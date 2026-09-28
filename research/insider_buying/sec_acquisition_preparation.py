"""Zero-I/O SEC acquisition recipes and non-verbatim header projections.

Targets, capture provenance and XML filenames are caller declarations, not
authenticated evidence or approved sample selections. No request is executed;
the derived JSON is not authorized input to the existing IB-1C boundary.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAvailabilityRecord,
    SecEdgarAvailabilityRule,
    SecEdgarAvailabilityTier,
    SecEdgarAcceptanceSnapshotError,
)
from research.insider_buying.sec_noncanonical_pilot_contracts import (
    PilotAccessionCandidateIdentity,
    SecNoncanonicalPilotContractError,
)


SEC_ACQUISITION_PREPARATION_VERSION = "INSETF-SEC-ACQUISITION-PREPARATION-v1"
SEC_HEADER_PROJECTION_VERSION = "INSETF-SEC-HEADER-PROJECTION-v1"
SEC_HEADER_TIMEZONE_POLICY = "sec-header-eastern-2022q4-2023q1-v1"
SEC_ACQUISITION_MAX_TARGETS = 64
MAX_SEC_HEADER_BYTES = 2 * 1024 * 1024
_PERIODS = ("2022Q4", "2023Q1")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_GIT = re.compile(r"^[0-9a-f]{40}$")
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*\.xml$")
_TARGET_FIELDS = (
    "period", "accession_number", "form_type", "filing_date", "issuer_cik",
    "quarterly_zip_sha256", "submission_row_id", "primary_xml_filename",
)
_TRANSFORMS = {
    "accession_number": "sec-header-accession-number-v1",
    "form_type": "sec-header-conformed-submission-type-v1",
    "filing_date": "sec-header-filed-as-of-date-yyyymmdd-to-iso-v1",
    "accepted_at": "sec-header-acceptance-datetime-eastern-2022q4-2023q1-v1",
    "primary_document_url": "caller-declared-filename-plus-candidate-issuer-archives-path-v1",
}


class SecAcquisitionPreparationError(ValueError):
    """The non-executable preparation recipe failed closed."""


def _authority() -> dict[str, object]:
    return {
        "network_access_authorized": False,
        "pilot_execution_authorized": False,
        "direct_ib1c_ingest_authorized": False,
        "official_sec_profile_verified": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "source_authenticated": False,
        "target_inventory_verified": False,
        "sample_owner_approved": False,
        "completeness_verified": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }


def _target_values(target: SecAcquisitionTarget) -> dict[str, str]:
    if type(target) is not SecAcquisitionTarget:
        raise SecAcquisitionPreparationError("REFUSED: an exact acquisition target is required")
    values = {name: getattr(target, name) for name in _TARGET_FIELDS}
    if any(type(value) is not str for value in values.values()):
        raise SecAcquisitionPreparationError("REFUSED: target fields must be exact strings")
    if target.period not in _PERIODS:
        raise SecAcquisitionPreparationError("REFUSED: target lies outside 2022Q4..2023Q1")
    if _SHA.fullmatch(target.submission_row_id) is None:
        raise SecAcquisitionPreparationError("REFUSED: submission row identity is invalid")
    filename = target.primary_xml_filename
    if (len(filename) > 255 or _FILENAME.fullmatch(filename) is None
            or filename.casefold().startswith("xsl")):
        raise SecAcquisitionPreparationError("REFUSED: primary filename must be a raw root XML filename")
    try:
        PilotAccessionCandidateIdentity(
            period=target.period, accession_number=target.accession_number,
            form_type=target.form_type, filing_date=target.filing_date,
            issuer_cik=target.issuer_cik,
            quarterly_zip_sha256=target.quarterly_zip_sha256,
            submission_row_sha256=target.submission_row_id,
        )
    except SecNoncanonicalPilotContractError as exc:
        raise SecAcquisitionPreparationError(str(exc)) from exc
    return values


@dataclass(frozen=True)
class SecAcquisitionTarget:
    period: str
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    quarterly_zip_sha256: str
    submission_row_id: str
    primary_xml_filename: str

    def __post_init__(self) -> None:
        _target_values(self)

    def to_payload(self) -> dict[str, str]:
        return _target_values(self)

    @property
    def archive_root(self) -> str:
        _target_values(self)
        return ("https://www.sec.gov/Archives/edgar/data/"
                f"{int(self.issuer_cik)}/{self.accession_number.replace('-', '')}/")

    @property
    def header_url(self) -> str:
        return self.archive_root + self.accession_number + ".hdr.sgml"

    @property
    def index_url(self) -> str:
        return self.archive_root + self.accession_number + "-index.htm"

    @property
    def primary_xml_url(self) -> str:
        return self.archive_root + self.primary_xml_filename


def _copy_target(target: object) -> SecAcquisitionTarget:
    if type(target) is not SecAcquisitionTarget:
        raise SecAcquisitionPreparationError("REFUSED: an exact acquisition target is required")
    return SecAcquisitionTarget(**_target_values(target))


def _ordered_targets(targets: object) -> tuple[SecAcquisitionTarget, ...]:
    if type(targets) is not tuple or not 1 <= len(targets) <= SEC_ACQUISITION_MAX_TARGETS:
        raise SecAcquisitionPreparationError("REFUSED: plan requires 1..64 exact targets")
    copied = tuple(_copy_target(target) for target in targets)
    if len({target.accession_number for target in copied}) != len(copied):
        raise SecAcquisitionPreparationError("REFUSED: duplicate target accession")
    return tuple(sorted(copied, key=lambda item: (item.period, item.accession_number)))


@dataclass(frozen=True)
class SecAcquisitionPlan:
    targets: tuple[SecAcquisitionTarget, ...]

    def __post_init__(self) -> None:
        if type(self) is not SecAcquisitionPlan:
            raise SecAcquisitionPreparationError("REFUSED: an exact acquisition plan is required")
        object.__setattr__(self, "targets", _ordered_targets(self.targets))

    def to_payload(self) -> dict[str, object]:
        if type(self) is not SecAcquisitionPlan:
            raise SecAcquisitionPreparationError("REFUSED: an exact acquisition plan is required")
        ordered = _ordered_targets(self.targets)
        if ordered != self.targets:
            raise SecAcquisitionPreparationError("REFUSED: plan target order was altered")
        return {
            "version": SEC_ACQUISITION_PREPARATION_VERSION,
            "targets": [target.to_payload() for target in ordered],
            "requests": [{
                "target_accession": target.accession_number,
                "header_url": target.header_url,
                "index_url": target.index_url,
                "primary_xml_url": target.primary_xml_url,
            } for target in ordered],
            "transport_policy": {
                "current_external_request_budget": 0,
                "requests_per_second_ceiling": 2,
                "max_attempts_per_artifact": 3,
                "redirects_allowed": False,
                "identifying_contact_required": True,
                "backoff_and_checkpoint_required": True,
                "immutable_accession_cache_required": True,
                "executable_transport_supplied": False,
            },
            "authority": _authority(),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def build_sec_acquisition_plan(targets: tuple[SecAcquisitionTarget, ...]) -> SecAcquisitionPlan:
    return SecAcquisitionPlan(targets)


def _unique_line(block: str, label: str) -> str:
    lines = re.findall(r"(?m)^[ \t]*" + re.escape(label) + r":[^\r\n]*", block)
    if len(lines) != 1:
        raise SecAcquisitionPreparationError(f"REFUSED: missing or ambiguous {label}")
    return lines[0].split(":", 1)[1].strip()


def _header_fields(raw: bytes) -> dict[str, str]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_SEC_HEADER_BYTES:
        raise SecAcquisitionPreparationError("REFUSED: header must be a nonempty bounded exact byte image")
    if b"\x00" in raw:
        raise SecAcquisitionPreparationError("REFUSED: header contains NUL")
    if any(byte < 32 and byte not in {9, 10, 13} for byte in raw):
        raise SecAcquisitionPreparationError("REFUSED: header contains unsupported control bytes")
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise SecAcquisitionPreparationError("REFUSED: header must be strict ASCII") from exc
    starts = list(re.finditer(r"(?m)^<SEC-HEADER>[^\r\n]*\r?$", text))
    ends = list(re.finditer(r"(?m)^</SEC-HEADER>\r?$", text))
    if (len(starts) != 1 or len(ends) != 1
            or text.count("<SEC-HEADER>") != 1 or text.count("</SEC-HEADER>") != 1
            or starts[0].end() >= ends[0].start()
            or text[:starts[0].start()].strip() or text[ends[0].end():].strip()):
        raise SecAcquisitionPreparationError("REFUSED: exactly one complete SEC-HEADER block is required")
    block = text[starts[0].end():ends[0].start()]
    role_names = r"(?:REPORTING-OWNER|FILED BY|SUBJECT COMPANY|FILER|ISSUER)"
    all_roles = re.finditer(r"(?m)^[ \t]*" + role_names + r":[ \t]*\r?$", block)
    if any(match.group(0).startswith((" ", "\t")) for match in all_roles):
        raise SecAcquisitionPreparationError("REFUSED: root roles must begin at column zero")
    root_section_pattern = r"(?m)^" + role_names + r":[ \t]*\r?$"
    first_section = re.search(root_section_pattern, block)
    preamble = block[:first_section.start()] if first_section else block
    labels = ("ACCESSION NUMBER", "CONFORMED SUBMISSION TYPE", "FILED AS OF DATE")
    for label in labels:
        # Refuse both duplicate fields anywhere and single fields hidden inside
        # an unrelated role. Only the header preamble describes this filing.
        if _unique_line(block, label) != _unique_line(preamble, label):
            raise SecAcquisitionPreparationError("REFUSED: filing field is outside the preamble")
        if len(re.findall(r"(?m)^" + re.escape(label) + r":[^\r\n]*", preamble)) != 1:
            raise SecAcquisitionPreparationError("REFUSED: filing fields must begin at column zero")
    acceptance = re.findall(r"(?m)^[ \t]*<ACCEPTANCE-DATETIME>[^\r\n]*", block)
    if (len(acceptance) != 1 or block.count("<ACCEPTANCE-DATETIME>") != 1
            or len(re.findall(r"(?m)^<ACCEPTANCE-DATETIME>[^\r\n]*", preamble)) != 1):
        raise SecAcquisitionPreparationError("REFUSED: missing or ambiguous acceptance timestamp")
    accepted_raw = acceptance[0].strip().removeprefix("<ACCEPTANCE-DATETIME>")
    if re.fullmatch(r"[0-9]{14}", accepted_raw) is None:
        raise SecAcquisitionPreparationError("REFUSED: acceptance requires exactly fourteen digits")
    issuers = list(re.finditer(r"(?m)^ISSUER:[ \t]*\r?$", block))
    if len(issuers) != 1:
        raise SecAcquisitionPreparationError("REFUSED: exactly one ISSUER section is required")
    issuer_tail = block[issuers[0].end():]
    next_section = re.search(root_section_pattern, issuer_tail)
    issuer_block = issuer_tail[:next_section.start()] if next_section else issuer_tail
    company_sections = list(re.finditer(r"(?m)^[ \t]*COMPANY DATA:[ \t]*\r?$", issuer_block))
    if len(company_sections) != 1:
        raise SecAcquisitionPreparationError("REFUSED: issuer requires one COMPANY DATA section")
    if issuer_block[:company_sections[0].start()].strip():
        raise SecAcquisitionPreparationError("REFUSED: COMPANY DATA must be the first issuer subsection")
    company_tail = issuer_block[company_sections[0].end():]
    next_subsection = re.search(r"(?m)^[ \t]*(?:BUSINESS ADDRESS|MAIL ADDRESS|FORMER COMPANY|FILING VALUES):[ \t]*\r?$", company_tail)
    company_block = company_tail[:next_subsection.start()] if next_subsection else company_tail
    cik = _unique_line(company_block, "CENTRAL INDEX KEY")
    if _unique_line(issuer_block, "CENTRAL INDEX KEY") != cik:
        raise SecAcquisitionPreparationError("REFUSED: issuer CIK is outside COMPANY DATA")
    if re.fullmatch(r"[0-9]{1,10}", cik) is None or int(cik) == 0:
        raise SecAcquisitionPreparationError("REFUSED: issuer CIK is invalid")
    return {
        "accession_number": _unique_line(preamble, "ACCESSION NUMBER"),
        "form_type": _unique_line(preamble, "CONFORMED SUBMISSION TYPE"),
        "filing_date_raw": _unique_line(preamble, "FILED AS OF DATE"),
        "accepted_at_raw": accepted_raw,
        "issuer_cik_raw": cik,
    }


def _eastern_timestamp(raw: str) -> datetime:
    try:
        value = datetime(int(raw[:4]), int(raw[4:6]), int(raw[6:8]),
                         int(raw[8:10]), int(raw[10:12]), int(raw[12:14]))
    except ValueError as exc:
        raise SecAcquisitionPreparationError("REFUSED: acceptance is not a real local timestamp") from exc
    if not datetime(2022, 10, 1) <= value < datetime(2023, 4, 1):
        raise SecAcquisitionPreparationError("REFUSED: timestamp is outside the frozen Eastern policy")
    if datetime(2022, 11, 6, 1) <= value < datetime(2022, 11, 6, 2):
        raise SecAcquisitionPreparationError("REFUSED: ambiguous Eastern timestamp")
    if datetime(2023, 3, 12, 2) <= value < datetime(2023, 3, 12, 3):
        raise SecAcquisitionPreparationError("REFUSED: nonexistent Eastern timestamp")
    daylight = value < datetime(2022, 11, 6, 1) or value >= datetime(2023, 3, 12, 3)
    return value.replace(tzinfo=timezone(timedelta(hours=-4 if daylight else -5)))


@dataclass(frozen=True)
class SecHeaderMetadataProjection:
    target: SecAcquisitionTarget
    header_bytes: bytes
    source_url: str
    retrieved_at: datetime
    capture_git_commit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _copy_target(self.target))
        retrieved_utc = self._validated()[2]
        object.__setattr__(self, "retrieved_at", datetime.fromisoformat(retrieved_utc))
        self._validated()

    def _validated(self) -> tuple[dict[str, str], dict[str, str], str]:
        if type(self) is not SecHeaderMetadataProjection:
            raise SecAcquisitionPreparationError("REFUSED: an exact header projection is required")
        target = _copy_target(self.target)
        if type(self.source_url) is not str or self.source_url != target.header_url:
            raise SecAcquisitionPreparationError("REFUSED: header URL must match the exact target archive path")
        if type(self.capture_git_commit) is not str or _GIT.fullmatch(self.capture_git_commit) is None:
            raise SecAcquisitionPreparationError("REFUSED: capture commit must be a full lowercase Git SHA")
        if type(self.retrieved_at) is not datetime:
            raise SecAcquisitionPreparationError("REFUSED: retrieval must be an exact aware datetime")
        if type(self.retrieved_at.tzinfo) is not timezone:
            # No caller-owned callback may run during a zero-I/O capture
            # contract, including custom tzinfo and host ZoneInfo providers.
            raise SecAcquisitionPreparationError("REFUSED: retrieval requires a fixed datetime.timezone offset")
        try:
            offset = self.retrieved_at.utcoffset()
            retrieved_utc = self.retrieved_at.astimezone(timezone.utc)
        except (OverflowError, ValueError, TypeError) as exc:
            raise SecAcquisitionPreparationError("REFUSED: retrieval timestamp is invalid") from exc
        if offset is None or self.retrieved_at.microsecond != 0:
            raise SecAcquisitionPreparationError("REFUSED: retrieval must be aware at exact seconds")
        fields = _header_fields(self.header_bytes)
        if (fields["accession_number"] != target.accession_number
                or fields["form_type"] != target.form_type
                or fields["filing_date_raw"] != target.filing_date.replace("-", "")
                or fields["issuer_cik_raw"].zfill(10) != target.issuer_cik):
            raise SecAcquisitionPreparationError("REFUSED: header disagrees with the declared target")
        accepted = _eastern_timestamp(fields["accepted_at_raw"])
        if retrieved_utc < accepted.astimezone(timezone.utc):
            raise SecAcquisitionPreparationError("REFUSED: retrieval precedes acceptance")
        try:
            SecEdgarAvailabilityRecord(
                accession_number=target.accession_number, document_type=target.form_type,
                submission_row_id=target.submission_row_id,
                filing_date=date.fromisoformat(target.filing_date),
                availability_tier=SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP,
                next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
                accepted_at=accepted, primary_document_url=target.primary_xml_url,
                metadata_source_sha256=hash_bytes(self.header_bytes),
            )
        except SecEdgarAcceptanceSnapshotError as exc:
            raise SecAcquisitionPreparationError(str(exc)) from exc
        flat = {
            "accession_number": target.accession_number,
            "form_type": target.form_type,
            "filing_date": target.filing_date,
            "accepted_at": accepted.isoformat(timespec="seconds"),
            "primary_document_url": target.primary_xml_url,
        }
        return fields, flat, retrieved_utc.isoformat(timespec="seconds")

    def flat_payload(self) -> dict[str, str]:
        return self._validated()[1]

    @property
    def accepted_at_text(self) -> str:
        return self.flat_payload()["accepted_at"]

    @property
    def raw_acceptance_text(self) -> str:
        return self._validated()[0]["accepted_at_raw"]

    @property
    def header_sha256(self) -> str:
        self._validated()
        return hash_bytes(self.header_bytes)

    @property
    def derived_json_bytes(self) -> bytes:
        return (canonical_json(self.flat_payload()) + "\n").encode("utf-8")

    @property
    def derived_json_sha256(self) -> str:
        return hash_bytes(self.derived_json_bytes)

    def to_payload(self) -> dict[str, object]:
        fields, flat, retrieved_utc = self._validated()
        derived = (canonical_json(flat) + "\n").encode("utf-8")
        profile = {
            "profile_id": "nonverbatim-sec-header-flat-json-v1",
            "exact_fields": sorted(flat),
            "periods": list(_PERIODS),
            "field_transforms": dict(_TRANSFORMS),
            "timezone_policy": SEC_HEADER_TIMEZONE_POLICY,
            "official_sec_profile_verified": False,
            "direct_ib1c_ingest_authorized": False,
        }
        return {
            "version": SEC_HEADER_PROJECTION_VERSION,
            "target": self.target.to_payload(),
            "raw_header": {
                "sha256": hash_bytes(self.header_bytes),
                "size_bytes": len(self.header_bytes),
                "bytes_base64": base64.b64encode(self.header_bytes).decode("ascii"),
                "source_url": self.source_url,
                "retrieved_at_utc": retrieved_utc,
                "capture_git_commit": self.capture_git_commit,
            },
            "source_fields": fields,
            "flat_payload": flat,
            "derivation": {
                "timezone_policy": SEC_HEADER_TIMEZONE_POLICY,
                "timezone_interpretation_verified": False,
                "field_transforms": dict(_TRANSFORMS),
                "primary_xml_filename_caller_declared": True,
                "primary_document_url_verified": False,
                "verbatim_sec_json_claim": False,
                "amendment_original_inferred": False,
            },
            "derived_json": {
                "sha256": hash_bytes(derived), "size_bytes": len(derived),
                "encoding": "utf-8", "terminal_lf_count": 1,
                "profile": profile, "profile_sha256": hash_payload(profile),
            },
            "authority": _authority(),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def derive_sec_header_projection(
    target: SecAcquisitionTarget, header_bytes: bytes, *, source_url: str,
    retrieved_at: datetime, capture_git_commit: str,
) -> SecHeaderMetadataProjection:
    return SecHeaderMetadataProjection(
        target=_copy_target(target), header_bytes=header_bytes, source_url=source_url,
        retrieved_at=retrieved_at, capture_git_commit=capture_git_commit,
    )
