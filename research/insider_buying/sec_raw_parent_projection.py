"""Versioned, synthetic-only raw SEC parent and derived projection contract.

This module accepts caller-supplied bytes in memory. It never retrieves a
filing, reads a path, authenticates SEC provenance, or invokes IB-1C. A
matching hash proves only that the projection binds the supplied byte image.
The tagged-header dialect is separate from the frozen colon-header v1 recipe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
import xml.etree.ElementTree as ET

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_acquisition_preparation import (
    MAX_SEC_HEADER_BYTES,
    SecAcquisitionPreparationError,
    SecAcquisitionTarget,
    _copy_target,
    _eastern_timestamp,
)
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAcceptanceSnapshotError,
    SecEdgarAvailabilityRecord,
    SecEdgarAvailabilityRule,
    SecEdgarAvailabilityTier,
)


SEC_RAW_PARENT_PROJECTION_VERSION = "INSETF-SEC-RAW-PARENT-PROJECTION-v1"
SEC_TAG_MULTI_OWNER_HEADER_VERSION = "sec-tag-header-multi-owner-v1"
SEC_RAW_PARENT_MAX_BYTES = 2 * 1024 * 1024
SEC_RAW_PARENT_MAX_INDEX_ITEMS = 512
SEC_RAW_PARENT_MAX_OWNERS = 256
_XML_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*\.xml\Z")
_TAG_FIELD = re.compile(r"<([A-Z][A-Z0-9-]*)>([^<>\r\n]+)\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_XML_DECLARATION = re.compile(
    r"\A<\?xml\s+version=['\"]1\.0['\"](?:\s+encoding=['\"]UTF-8['\"])?"
    r"(?:\s+standalone=['\"](?:yes|no)['\"])?\s*\?>",
    flags=re.IGNORECASE,
)
_ROOT_MARKERS = frozenset({
    "<REPORTING-OWNER>", "</REPORTING-OWNER>", "<ISSUER>", "</ISSUER>",
})
_PREAMBLE_TAGS = frozenset({
    "ACCEPTANCE-DATETIME", "ACCESSION-NUMBER", "TYPE",
    "PUBLIC-DOCUMENT-COUNT", "PERIOD", "FILING-DATE",
    "DATE-OF-FILING-DATE-CHANGE",
})
# Real SEC tagged headers follow each role's data block with flat subsections
# (every one of the 16 acquired pilot headers does). Only these names are
# admitted, they may carry no CIK or nested scope, and only former-company
# blocks may repeat; anything else still refuses.
_OWNER_SUBSECTIONS = frozenset({"FILING-VALUES", "BUSINESS-ADDRESS", "MAIL-ADDRESS"})
_ISSUER_SUBSECTIONS = frozenset({"BUSINESS-ADDRESS", "MAIL-ADDRESS", "FORMER-COMPANY"})
_REPEATABLE_SUBSECTIONS = frozenset({"FORMER-COMPANY"})
_SCOPE_LINE = re.compile(r"<([A-Z][A-Z0-9-]*)>\Z")


class SecRawParentProjectionError(ValueError):
    """A supplied parent or its derived identity is incomplete or ambiguous."""


def _raw_bytes(value: object, *, label: str) -> bytes:
    if type(value) is not bytes or not 0 < len(value) <= SEC_RAW_PARENT_MAX_BYTES:
        raise SecRawParentProjectionError(
            f"REFUSED: {label} must be a nonempty bounded exact byte image"
        )
    return value


def _cik(value: object, *, label: str) -> str:
    if type(value) is not str or _CIK.fullmatch(value) is None or int(value) == 0:
        raise SecRawParentProjectionError(f"REFUSED: {label} is not an exact SEC CIK")
    return value.zfill(10)


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SecRawParentProjectionError("REFUSED: index repeats a JSON key")
        result[key] = value
    return result


def _refuse_non_json_constant(_: str) -> object:
    raise SecRawParentProjectionError("REFUSED: index contains a non-JSON constant")


def _index_filename(raw: bytes) -> str:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=_json_pairs,
            parse_constant=_refuse_non_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SecRawParentProjectionError("REFUSED: index is not strict JSON") from exc
    if type(value) is not dict or type(value.get("directory")) is not dict:
        raise SecRawParentProjectionError("REFUSED: index has no directory object")
    items = value["directory"].get("item")
    if type(items) is not list or not 1 <= len(items) <= SEC_RAW_PARENT_MAX_INDEX_ITEMS:
        raise SecRawParentProjectionError("REFUSED: index has no bounded item list")
    names: list[str] = []
    for item in items:
        if type(item) is not dict or type(item.get("name")) is not str:
            raise SecRawParentProjectionError("REFUSED: index item lacks an exact name")
        name = item["name"]
        if name.lower().endswith(".xml"):
            if (len(name) > 255 or _XML_NAME.fullmatch(name) is None
                    or name.casefold().startswith("xsl")):
                raise SecRawParentProjectionError("REFUSED: index XML name is unsafe")
            names.append(name)
    if len(names) != 1:
        raise SecRawParentProjectionError("REFUSED: index XML choice is absent or ambiguous")
    return names[0]


def _tag_value(lines: list[str], tag: str, *, label: str) -> str:
    prefix = f"<{tag}>"
    values = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    if len(values) != 1 or not values[0] or values[0] != values[0].strip():
        raise SecRawParentProjectionError(f"REFUSED: {label} {tag} is missing or ambiguous")
    return values[0]


def _company_cik(lines: list[str], *, outer: str) -> str:
    data = "<OWNER-DATA>" if outer == "owner" else "<COMPANY-DATA>"
    end = "</OWNER-DATA>" if outer == "owner" else "</COMPANY-DATA>"
    if len(lines) < 3 or lines[0] != data or lines.count(end) != 1:
        raise SecRawParentProjectionError(f"REFUSED: {outer} data scope is incomplete")
    data_end = lines.index(end)
    contents = lines[1:data_end]
    forbidden = _PREAMBLE_TAGS | _OWNER_SUBSECTIONS | _ISSUER_SUBSECTIONS | {
        "OWNER-DATA", "COMPANY-DATA", "REPORTING-OWNER", "ISSUER", "SEC-HEADER",
    }
    if not contents or any((match := _TAG_FIELD.fullmatch(line)) is None
                           or match.group(1) in forbidden for line in contents):
        raise SecRawParentProjectionError(f"REFUSED: {outer} data has nested or malformed fields")
    allowed = _OWNER_SUBSECTIONS if outer == "owner" else _ISSUER_SUBSECTIONS
    seen: set[str] = set()
    position = data_end + 1
    while position < len(lines):
        opening = _SCOPE_LINE.fullmatch(lines[position])
        name = opening.group(1) if opening else None
        if (name not in allowed
                or (name in seen and name not in _REPEATABLE_SUBSECTIONS)):
            raise SecRawParentProjectionError(
                f"REFUSED: {outer} has an unsupported or repeated subsection"
            )
        seen.add(name)
        closing = f"</{name}>"
        if closing not in lines[position + 1:]:
            raise SecRawParentProjectionError(f"REFUSED: {outer} subsection is unbalanced")
        close = lines.index(closing, position + 1)
        if any((match := _TAG_FIELD.fullmatch(line)) is None
               or match.group(1) in forbidden or match.group(1) == "CIK"
               for line in lines[position + 1:close]):
            raise SecRawParentProjectionError(
                f"REFUSED: {outer} subsection has nested, malformed, or identity fields"
            )
        position = close + 1
    raw = _tag_value(contents, "CIK", label=outer)
    if sum(line.startswith("<CIK>") for line in lines) != 1:
        raise SecRawParentProjectionError(f"REFUSED: {outer} CIK is ambiguous")
    _cik(raw, label=f"{outer} CIK")
    return raw


def _header_fields(raw: bytes, target: SecAcquisitionTarget) -> dict[str, object]:
    if len(raw) > MAX_SEC_HEADER_BYTES or b"\x00" in raw or any(
        byte < 32 and byte not in (9, 10, 13) for byte in raw
    ):
        raise SecRawParentProjectionError("REFUSED: header has unsupported bytes")
    try:
        text = raw.decode("ascii", errors="strict").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise SecRawParentProjectionError("REFUSED: header is not strict ASCII") from exc
    if "\r" in text:
        raise SecRawParentProjectionError("REFUSED: header has unsupported line endings")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    expected_open = (
        f"<SEC-HEADER>{target.accession_number}.hdr.sgml : "
        f"{target.filing_date.replace('-', '')}"
    )
    if (len(lines) < 8 or lines[0] != expected_open or lines[-1] != "</SEC-HEADER>"
            or sum(line.startswith("<SEC-HEADER>") for line in lines) != 1
            or lines.count("</SEC-HEADER>") != 1):
        raise SecRawParentProjectionError("REFUSED: header envelope disagrees with target")
    body = lines[1:-1]
    markers = [(position, line) for position, line in enumerate(body) if line in _ROOT_MARKERS]
    if (not markers or sum(line.count(marker) for line in body for marker in _ROOT_MARKERS)
            != len(markers)):
        raise SecRawParentProjectionError("REFUSED: header has a nested or disguised root role")
    ordered = [marker for _, marker in markers]
    owner_count = (len(ordered) - 2) // 2
    if (not 1 <= owner_count <= SEC_RAW_PARENT_MAX_OWNERS
            or ordered != ["<REPORTING-OWNER>", "</REPORTING-OWNER>"] * owner_count
            + ["<ISSUER>", "</ISSUER>"]):
        raise SecRawParentProjectionError("REFUSED: header role topology is ambiguous")
    if markers[-1][0] != len(body) - 1:
        raise SecRawParentProjectionError("REFUSED: header has content after issuer")
    preamble = body[:markers[0][0]]
    for line in preamble:
        match = _TAG_FIELD.fullmatch(line)
        if match is None or match.group(1) not in _PREAMBLE_TAGS:
            raise SecRawParentProjectionError("REFUSED: header preamble contains a foreign field")
    required = ("ACCESSION-NUMBER", "TYPE", "FILING-DATE", "ACCEPTANCE-DATETIME")
    values = {tag: _tag_value(preamble, tag, label="header") for tag in required}
    for tag in required:
        if sum(line.startswith(f"<{tag}>") for line in body) != 1:
            raise SecRawParentProjectionError(f"REFUSED: header {tag} is repeated outside preamble")
    if (values["ACCESSION-NUMBER"] != target.accession_number
            or values["TYPE"] != target.form_type
            or values["FILING-DATE"] != target.filing_date.replace("-", "")
            or re.fullmatch(r"[0-9]{14}", values["ACCEPTANCE-DATETIME"]) is None):
        raise SecRawParentProjectionError("REFUSED: header identity disagrees with target")
    owners: list[str] = []
    for index in range(owner_count):
        opening = markers[2 * index][0]
        closing = markers[2 * index + 1][0]
        if closing <= opening + 1:
            raise SecRawParentProjectionError("REFUSED: reporting-owner role is empty")
        owners.append(_company_cik(body[opening + 1:closing], outer="owner"))
    issuer_open, issuer_close = markers[-2][0], markers[-1][0]
    if issuer_open != markers[-3][0] + 1:
        raise SecRawParentProjectionError("REFUSED: header has content between owner and issuer")
    for index in range(owner_count - 1):
        if markers[2 * index + 2][0] != markers[2 * index + 1][0] + 1:
            raise SecRawParentProjectionError("REFUSED: header has content between owners")
    issuer_raw = _company_cik(body[issuer_open + 1:issuer_close], outer="issuer")
    if _cik(issuer_raw, label="issuer CIK") != target.issuer_cik:
        raise SecRawParentProjectionError("REFUSED: header issuer disagrees with target")
    normalized = [_cik(owner, label="owner CIK") for owner in owners]
    if len(set(normalized)) != len(normalized):
        raise SecRawParentProjectionError("REFUSED: header repeats a reporting-owner CIK")
    try:
        accepted = _eastern_timestamp(values["ACCEPTANCE-DATETIME"])
        SecEdgarAvailabilityRecord(
            accession_number=target.accession_number, document_type=target.form_type,
            submission_row_id=target.submission_row_id,
            filing_date=date.fromisoformat(target.filing_date),
            availability_tier=SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP,
            next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
            accepted_at=accepted, primary_document_url=target.primary_xml_url,
            metadata_source_sha256=hash_bytes(raw),
        )
    except (SecAcquisitionPreparationError, SecEdgarAcceptanceSnapshotError) as exc:
        raise SecRawParentProjectionError(str(exc)) from exc
    return {
        "accession_number": values["ACCESSION-NUMBER"],
        "form_type": values["TYPE"],
        "filing_date_raw": values["FILING-DATE"],
        "accepted_at_raw": values["ACCEPTANCE-DATETIME"],
        "accepted_at_interpretation": accepted.isoformat(timespec="seconds"),
        "issuer_cik_raw": issuer_raw,
        "header_owner_ciks_raw": owners,
        "header_owner_ciks_normalized": normalized,
    }


def _xml_fields(raw: bytes, target: SecAcquisitionTarget) -> dict[str, object]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SecRawParentProjectionError("REFUSED: XML is not strict UTF-8") from exc
    if text.startswith("\ufeff"):
        raise SecRawParentProjectionError("REFUSED: XML has a BOM")
    declaration = _XML_DECLARATION.match(text)
    if re.search(r"<\?xml", text, flags=re.IGNORECASE) and declaration is None:
        raise SecRawParentProjectionError("REFUSED: XML has a foreign declaration")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise SecRawParentProjectionError("REFUSED: XML declares a DTD or entity")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SecRawParentProjectionError("REFUSED: XML is malformed") from exc
    if any(type(node.tag) is not str or "{" in node.tag or "}" in node.tag
           or ":" in node.tag for node in root.iter()):
        raise SecRawParentProjectionError("REFUSED: XML namespace-qualified nodes are unsupported")
    if root.tag != "ownershipDocument":
        raise SecRawParentProjectionError("REFUSED: XML root is not ownershipDocument")
    if (len(root.findall("documentType")) != 1
            or len(list(root.iter("documentType"))) != 1
            or len(root.findall("issuer")) != 1
            or len(root.findall("issuer/issuerCik")) != 1
            or len(list(root.iter("issuerCik"))) != 1):
        raise SecRawParentProjectionError("REFUSED: XML form or issuer is ambiguous")
    form = _scalar_xml_identity(root.find("documentType"), label="XML form")
    issuer = _scalar_xml_identity(root.find("issuer/issuerCik"), label="XML issuer CIK")
    if (form != target.form_type or type(issuer) is not str
            or _cik(issuer, label="XML issuer CIK") != target.issuer_cik):
        raise SecRawParentProjectionError("REFUSED: XML form or issuer disagrees with target")
    owner_blocks = root.findall("reportingOwner")
    if (not 1 <= len(owner_blocks) <= SEC_RAW_PARENT_MAX_OWNERS
            or len(list(root.iter("reportingOwner"))) != len(owner_blocks)):
        raise SecRawParentProjectionError("REFUSED: XML owner topology is ambiguous")
    owners: list[str] = []
    for block in owner_blocks:
        if (len(block.findall("reportingOwnerId")) != 1
                or len(block.findall("reportingOwnerId/rptOwnerCik")) != 1
                or len(list(block.iter("rptOwnerCik"))) != 1):
            raise SecRawParentProjectionError("REFUSED: XML owner identity is ambiguous")
        raw_cik = _scalar_xml_identity(
            block.find("reportingOwnerId/rptOwnerCik"), label="XML owner CIK"
        )
        _cik(raw_cik, label="XML owner CIK")
        owners.append(raw_cik)
    normalized = [_cik(owner, label="XML owner CIK") for owner in owners]
    if len(set(normalized)) != len(normalized):
        raise SecRawParentProjectionError("REFUSED: XML repeats a reporting-owner CIK")
    return {
        "xml_form_type": form, "xml_issuer_cik_text": issuer,
        "xml_owner_ciks_text": owners,
        "xml_owner_ciks_normalized": normalized,
    }


def _scalar_xml_identity(node: ET.Element | None, *, label: str) -> str:
    if (node is None or node.attrib or len(node) or node.text is None
            or node.text != node.text.strip()
            or (node.tail is not None and node.tail.strip())):
        raise SecRawParentProjectionError(f"REFUSED: {label} is not one scalar leaf")
    return node.text


@dataclass(frozen=True)
class SecRawParentProjection:
    """Revalidated exact supplied bytes and a separate noncanonical projection."""

    target: SecAcquisitionTarget
    index_bytes: bytes
    header_bytes: bytes
    xml_bytes: bytes

    def __post_init__(self) -> None:
        if type(self) is not SecRawParentProjection:
            raise SecRawParentProjectionError("REFUSED: exact projection type required")
        try:
            object.__setattr__(self, "target", _copy_target(self.target))
        except SecAcquisitionPreparationError as exc:
            raise SecRawParentProjectionError(str(exc)) from exc
        self._validated()

    def _validated(self) -> tuple[SecAcquisitionTarget, dict[str, object], dict[str, object]]:
        if type(self) is not SecRawParentProjection:
            raise SecRawParentProjectionError("REFUSED: exact projection type required")
        try:
            target = _copy_target(self.target)
        except SecAcquisitionPreparationError as exc:
            raise SecRawParentProjectionError(str(exc)) from exc
        index = _raw_bytes(self.index_bytes, label="index")
        header = _raw_bytes(self.header_bytes, label="header")
        xml = _raw_bytes(self.xml_bytes, label="XML")
        if _index_filename(index) != target.primary_xml_filename:
            raise SecRawParentProjectionError("REFUSED: index XML differs from target")
        header_fields = _header_fields(header, target)
        xml_fields = _xml_fields(xml, target)
        if (len(header_fields["header_owner_ciks_normalized"])
                != len(xml_fields["xml_owner_ciks_normalized"])
                or set(header_fields["header_owner_ciks_normalized"])
                != set(xml_fields["xml_owner_ciks_normalized"])):
            raise SecRawParentProjectionError("REFUSED: header and XML owner sets disagree")
        return target, header_fields, xml_fields

    def flat_payload(self) -> dict[str, str]:
        target, header, _ = self._validated()
        return {
            "accession_number": target.accession_number,
            "form_type": target.form_type,
            "filing_date": target.filing_date,
            "accepted_at": header["accepted_at_interpretation"],
            "primary_document_url": target.primary_xml_url,
            "primary_document_sha256": hash_bytes(self.xml_bytes),
        }

    @property
    def derived_json_bytes(self) -> bytes:
        return (canonical_json(self.flat_payload()) + "\n").encode("utf-8")

    def to_payload(self) -> dict[str, object]:
        target, header, xml = self._validated()
        hashes = {
            "index": hash_bytes(self.index_bytes),
            "header": hash_bytes(self.header_bytes),
            "xml": hash_bytes(self.xml_bytes),
        }
        flat_bytes = self.derived_json_bytes
        flat = self.flat_payload()
        parents = {
            "index": {"declared_source_url": target.archive_root + "index.json",
                      "sha256": hashes["index"], "size_bytes": len(self.index_bytes)},
            "header": {"declared_source_url": target.header_url,
                       "sha256": hashes["header"], "size_bytes": len(self.header_bytes)},
            "xml": {"declared_source_url": target.primary_xml_url,
                    "sha256": hashes["xml"], "size_bytes": len(self.xml_bytes)},
        }
        source_fields = {
            **header, **xml, "index_primary_xml_filename": target.primary_xml_filename,
        }
        parent_identity = {
            "version": SEC_RAW_PARENT_PROJECTION_VERSION,
            "target": target.to_payload(),
            "raw_parents": parents,
            "source_fields": source_fields,
        }
        field_lineage = {
            "accession_number": {"source_role": "header", "source_sha256": hashes["header"],
                                 "transform": "exact-tag-value-crosschecked-with-target-v1"},
            "form_type": {"source_role": "header", "source_sha256": hashes["header"],
                          "transform": "exact-tag-value-crosschecked-with-target-and-xml-v1"},
            "filing_date": {"source_role": "header", "source_sha256": hashes["header"],
                            "transform": "yyyymmdd-to-iso-crosschecked-with-target-v1"},
            "accepted_at": {"source_role": "header", "source_sha256": hashes["header"],
                            "transform": "unverified-eastern-timezone-interpretation-v1"},
            "primary_document_url": {
                "source_role": "index", "source_sha256": hashes["index"],
                "transform": "index-xml-filename-plus-target-archive-root-v1",
            },
            "primary_document_sha256": {
                "source_role": "xml", "source_sha256": hashes["xml"],
                "transform": "sha256-exact-primary-xml-bytes-v1",
            },
        }
        return {
            "version": SEC_RAW_PARENT_PROJECTION_VERSION,
            "header_dialect_version": SEC_TAG_MULTI_OWNER_HEADER_VERSION,
            "target": parent_identity["target"],
            "raw_parents": parents,
            "raw_parent_identity_sha256": hash_payload(parent_identity),
            "source_fields": source_fields,
            "derived_projection": {
                "sha256": hash_bytes(flat_bytes), "size_bytes": len(flat_bytes),
                "format": "canonical-json-utf8-plus-one-lf",
                "flat_payload": flat,
                "reporting_owner_count": len(header["header_owner_ciks_raw"]),
                "buyer_attribution_available": False,
                "ib1c_profile_compatible": False,
                "amendment_original_accession_unavailable": target.form_type == "4/A",
                "field_lineage": field_lineage,
            },
            "authority": {
                "synthetic_only": True,
                "network_access_authorized": False,
                "direct_ib1c_ingest_authorized": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "source_authenticated": False,
                "official_sec_profile_verified": False,
                "timezone_interpretation_verified": False,
                "retrieval_timestamp_unavailable": True,
                "prior_code_sha_artifact_verified": False,
                "first_pass_pacing_trace_verified": False,
                "completeness_verified": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def derive_sec_raw_parent_projection(
    target: SecAcquisitionTarget, index_bytes: bytes, header_bytes: bytes,
    xml_bytes: bytes,
) -> SecRawParentProjection:
    """Bind exactly one accession's three supplied parents without I/O."""
    return SecRawParentProjection(target, index_bytes, header_bytes, xml_bytes)
