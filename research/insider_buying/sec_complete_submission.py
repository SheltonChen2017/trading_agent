"""Pure, bounded projection from a caller-supplied SEC complete submission.

The complete `.txt` image is the only raw parent. Header and ownership XML
bytes are verbatim slices of that image, not independently fetched SEC files.
The URL and index hash are caller declarations. The legacy-header path has
been replayed against 16 pinned pilot complete-submission byte images, while
the tagged-header path has synthetic coverage only. This pure projection does
no I/O, does not verify index membership or SEC authenticity, and grants no
PIT, canonical-source, IB-1C, outcome, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_raw_parent_projection import (
    SecRawParentProjectionError,
    _cik,
    _company_cik,
    _xml_fields,
)


SEC_COMPLETE_SUBMISSION_VERSION = "INSETF-SEC-COMPLETE-SUBMISSION-v1"
MAX_COMPLETE_SUBMISSION_BYTES = 8 * 1024 * 1024
# Count separators before splitlines: an 8 MiB image of one-byte lines would
# otherwise allocate millions of Python objects before any document guard.
# 100,000 is a conservative structural ceiling, not a measured SEC profile.
MAX_COMPLETE_SUBMISSION_LINES = 100_000
MAX_COMPLETE_HEADER_BYTES = 2 * 1024 * 1024
MAX_COMPLETE_XML_BYTES = 4 * 1024 * 1024
MAX_COMPLETE_DOCUMENTS = 32
MAX_COMPLETE_OWNERS = 256
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_ARCHIVE_URL = re.compile(
    r"https://www\.sec\.gov/Archives/edgar/data/"
    r"(?P<cik>[0-9]{1,10})/"
    r"(?:(?P<compact>[0-9]{18})/)?"
    r"(?P<accession>[0-9]{10}-[0-9]{2}-[0-9]{6})\.txt\Z"
)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
_XML_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,250}\.xml\Z")
_TAG_FIELD = re.compile(r"<([A-Z][A-Z0-9-]*)>([^<>\r\n]+)\Z")
_HEADER_PREAMBLE = frozenset({
    "ACCEPTANCE-DATETIME", "ACCESSION-NUMBER", "TYPE",
    "PUBLIC-DOCUMENT-COUNT", "PERIOD", "FILING-DATE",
    "DATE-OF-FILING-DATE-CHANGE",
})
_LEGACY_PREAMBLE = (
    "ACCESSION NUMBER", "CONFORMED SUBMISSION TYPE", "PUBLIC DOCUMENT COUNT",
    "CONFORMED PERIOD OF REPORT", "FILED AS OF DATE", "DATE AS OF CHANGE",
)
_LEGACY_ROLE = frozenset({"REPORTING-OWNER:", "ISSUER:"})
_LEGACY_OWNER_SCOPES = (
    "OWNER DATA", "FILING VALUES", "BUSINESS ADDRESS", "MAIL ADDRESS",
)
_LEGACY_ISSUER_SCOPES = (
    "COMPANY DATA", "BUSINESS ADDRESS", "MAIL ADDRESS", "FORMER COMPANY",
)
_LEGACY_FIELD = re.compile(r"([A-Z][A-Z0-9 -]*):[ \t]+([^\r\n]+)\Z")
_LEGACY_ROLE_LINE = re.compile(r"(REPORTING-OWNER:|ISSUER:)\t{0,4}\Z")
_LEGACY_SCOPE = re.compile(r"\t([A-Z][A-Z0-9 -]*):\t{0,4}\Z")
_LEGACY_LEAF = re.compile(r"\t\t([A-Z][A-Z0-9 -]*):[ \t]*([ -~]*)\Z")
_ROOT_MARKERS = frozenset({
    "<REPORTING-OWNER>", "</REPORTING-OWNER>", "<ISSUER>", "</ISSUER>",
})
_TARGET_FIELDS = (
    "period", "accession_number", "form_type", "filing_date", "issuer_cik",
    "quarterly_index_sha256", "complete_submission_url",
)


class SecCompleteSubmissionError(ValueError):
    """The supplied complete submission has an unsupported or unsafe shape."""


def _refuse(message: str) -> None:
    raise SecCompleteSubmissionError(f"REFUSED: {message}")


@dataclass(frozen=True)
class SecCompleteSubmissionTarget:
    period: str
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    quarterly_index_sha256: str
    complete_submission_url: str

    def __post_init__(self) -> None:
        self.to_payload()

    def to_payload(self) -> dict[str, str]:
        if type(self) is not SecCompleteSubmissionTarget:
            _refuse("an exact complete-submission target is required")
        values = {name: getattr(self, name) for name in _TARGET_FIELDS}
        if any(type(value) is not str for value in values.values()):
            _refuse("target fields must be exact strings")
        if _ACCESSION.fullmatch(self.accession_number) is None:
            _refuse("accession number is not canonical")
        if self.form_type not in {"4", "4/A"}:
            _refuse("only exact Form 4 or 4/A is a candidate")
        if _ISO_DATE.fullmatch(self.filing_date) is None:
            _refuse("filing date is not canonical")
        try:
            filed = date.fromisoformat(self.filing_date)
        except ValueError as exc:
            raise SecCompleteSubmissionError("REFUSED: filing date is invalid") from exc
        if not date(2006, 1, 1) <= filed <= date(2026, 6, 30):
            _refuse("filing date is outside the frozen source window")
        if self.period != f"{filed.year}Q{(filed.month - 1) // 3 + 1}":
            _refuse("filing period disagrees with filing date")
        if (not re.fullmatch(r"[0-9]{10}", self.issuer_cik)
                or int(self.issuer_cik) == 0):
            _refuse("issuer CIK is not ten padded nonzero digits")
        if _SHA.fullmatch(self.quarterly_index_sha256) is None:
            _refuse("quarterly index hash is not a lowercase SHA-256")
        match = _ARCHIVE_URL.fullmatch(self.complete_submission_url)
        if (match is None or int(match.group("cik")) == 0
                or match.group("accession") != self.accession_number
                or (match.group("compact") is not None
                    and match.group("compact") != self.accession_number.replace("-", ""))):
            _refuse("complete-submission URL is not the exact SEC accession path")
        # The archive-directory CIK is deliberately not equated to issuer CIK:
        # EDGAR may file an ownership form under a reporting person's CIK.
        return values


def _copy_target(value: object) -> SecCompleteSubmissionTarget:
    if type(value) is not SecCompleteSubmissionTarget:
        _refuse("an exact complete-submission target is required")
    return SecCompleteSubmissionTarget(**value.to_payload())


def _split_lines(raw: bytes) -> tuple[list[bytes], list[bytes]]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_COMPLETE_SUBMISSION_BYTES:
        _refuse("complete submission must be a nonempty bounded exact byte image")
    line_count = raw.count(b"\n") + (not raw.endswith(b"\n"))
    if line_count > MAX_COMPLETE_SUBMISSION_LINES:
        _refuse("complete submission line count exceeds its structural cap")
    if b"\x00" in raw or b"\r" in raw.replace(b"\r\n", b""):
        _refuse("complete submission has unsupported NUL or line endings")
    pieces = raw.splitlines(keepends=True)
    lines = [piece.removesuffix(b"\n").removesuffix(b"\r") for piece in pieces]
    if not lines:
        _refuse("complete submission has no lines")
    return pieces, lines


def _date_digits(value: bytes, *, label: str) -> str:
    if re.fullmatch(rb"[0-9]{8}", value) is None:
        _refuse(f"{label} is not an eight-digit date")
    try:
        date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as exc:
        raise SecCompleteSubmissionError(f"REFUSED: {label} is not a real date") from exc
    return value.decode("ascii")


def _unique_tag(lines: list[str], name: str, *, label: str) -> str:
    prefix = f"<{name}>"
    values = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    if len(values) != 1 or not values[0] or values[0] != values[0].strip():
        _refuse(f"{label} {name} is missing or ambiguous")
    return values[0]


def _legacy_role_cik(
    lines: list[str], *, owner: bool, target: SecCompleteSubmissionTarget,
) -> str:
    """Accept only the observed flat, tab-indented legacy SGML role shape."""
    allowed = _LEGACY_OWNER_SCOPES if owner else _LEGACY_ISSUER_SCOPES
    first = "OWNER DATA" if owner else "COMPANY DATA"
    scopes: list[str] = []
    fields: dict[str, dict[str, str]] = {}
    current: str | None = None
    seen_keys: set[str] = set()
    for line in lines:
        scope = _LEGACY_SCOPE.fullmatch(line)
        if scope is not None:
            name = scope.group(1)
            if name not in allowed or (scopes and not seen_keys):
                _refuse("legacy header has an empty or foreign role subsection")
            if not scopes and name != first:
                _refuse("legacy header data subsection is not first")
            if scopes and (allowed.index(name) < allowed.index(scopes[-1])
                           or (name == scopes[-1] and name != "FORMER COMPANY")):
                _refuse("legacy header role subsections are repeated or out of order")
            scopes.append(name)
            current = name
            seen_keys = set()
            if name != "FORMER COMPANY":
                fields[name] = {}
            continue
        leaf = _LEGACY_LEAF.fullmatch(line)
        if leaf is None or current is None:
            _refuse("legacy header role indentation or leaf is malformed")
        key, value = leaf.groups()
        if key in seen_keys:
            _refuse("legacy header role repeats a leaf")
        seen_keys.add(key)
        if (key in _LEGACY_PREAMBLE or key == "ACCEPTANCE-DATETIME"
                or key + ":" in _LEGACY_ROLE
                or key in _LEGACY_OWNER_SCOPES or key in _LEGACY_ISSUER_SCOPES):
            _refuse("legacy header repeats a preamble identity inside a role")
        if key == "CENTRAL INDEX KEY" and current != first:
            _refuse("legacy header CIK occurs outside the data subsection")
        if key == "FORM TYPE" and (not owner or current != "FILING VALUES"):
            _refuse("legacy header form type occurs outside owner filing values")
        if current != "FORMER COMPANY":
            fields[current][key] = value
    if not scopes or not seen_keys or first not in fields:
        _refuse("legacy header role is empty or lacks its data subsection")
    if owner and ("FILING VALUES" not in fields
                  or fields["FILING VALUES"].get("FORM TYPE") != target.form_type):
        _refuse("legacy header owner filing values disagree with target")
    cik_raw = fields[first].get("CENTRAL INDEX KEY")
    try:
        return _cik(cik_raw, label="legacy owner CIK" if owner else "legacy issuer CIK")
    except SecRawParentProjectionError as exc:
        raise SecCompleteSubmissionError(str(exc)) from exc


def _legacy_boundary_lines(lines: list[str], *, preceding: str) -> list[str]:
    """Discard only short SGML separator runs at explicit section boundaries."""
    result: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index] != "":
            result.append(lines[index])
            index += 1
            continue
        end = index
        while end < len(lines) and lines[end] == "":
            end += 1
        if end - index > 2:
            _refuse("legacy header has too many blank separator lines")
        previous = result[-1] if result else preceding
        following = lines[end] if end < len(lines) else None
        following_role = _LEGACY_ROLE_LINE.fullmatch(following) if following is not None else None
        after_preamble = (previous.startswith("DATE AS OF CHANGE:")
                          and following_role is not None
                          and following_role.group(1) == "REPORTING-OWNER:")
        after_role = (
            _LEGACY_ROLE_LINE.fullmatch(previous) is not None and following is not None
            and _LEGACY_SCOPE.fullmatch(following) is not None
        )
        after_leaf = (
            _LEGACY_LEAF.fullmatch(previous) is not None
            and (following is None or following_role is not None
                 or _LEGACY_SCOPE.fullmatch(following) is not None)
        )
        if not (after_preamble or after_role or after_leaf):
            _refuse("legacy header blank line is not a section separator")
        index = end
    return result


def _legacy_header_identity(
    body: list[str], target: SecCompleteSubmissionTarget,
) -> dict[str, object]:
    if len(body) < len(_LEGACY_PREAMBLE) + 4:
        _refuse("legacy header is incomplete")
    accepted_line = body[0]
    prefix = "<ACCEPTANCE-DATETIME>"
    if not accepted_line.startswith(prefix):
        _refuse("legacy header has no leading acceptance tag")
    accepted = accepted_line[len(prefix):]
    if re.fullmatch(r"[0-9]{14}", accepted) is None:
        _refuse("legacy acceptance timestamp is not fourteen digits")
    try:
        datetime.strptime(accepted, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise SecCompleteSubmissionError("REFUSED: legacy acceptance time is invalid") from exc
    preamble: dict[str, str] = {}
    for expected, line in zip(_LEGACY_PREAMBLE, body[1:1 + len(_LEGACY_PREAMBLE)], strict=True):
        match = _LEGACY_FIELD.fullmatch(line)
        if match is None or match.group(1) != expected or match.group(2) != match.group(2).strip():
            _refuse("legacy header preamble is malformed or out of order")
        preamble[expected] = match.group(2)
    if (preamble["ACCESSION NUMBER"] != target.accession_number
            or preamble["CONFORMED SUBMISSION TYPE"] != target.form_type
            or preamble["FILED AS OF DATE"] != target.filing_date.replace("-", "")):
        _refuse("legacy header accession, form, or filing date disagrees with target")
    if (re.fullmatch(r"[1-9][0-9]*", preamble["PUBLIC DOCUMENT COUNT"]) is None
            or int(preamble["PUBLIC DOCUMENT COUNT"]) > MAX_COMPLETE_DOCUMENTS):
        _refuse("legacy header public document count is invalid")
    for name in ("CONFORMED PERIOD OF REPORT", "DATE AS OF CHANGE"):
        _date_digits(preamble[name].encode("ascii"), label=f"legacy {name}")
    roles = _legacy_boundary_lines(
        body[1 + len(_LEGACY_PREAMBLE):], preceding=body[len(_LEGACY_PREAMBLE)],
    )
    markers = [
        (index, match.group(1)) for index, line in enumerate(roles)
        if (match := _LEGACY_ROLE_LINE.fullmatch(line)) is not None
    ]
    if (len(markers) < 2 or markers[0] != (0, "REPORTING-OWNER:")
            or markers[-1][1] != "ISSUER:" or any(
                line != "REPORTING-OWNER:" for _, line in markers[:-1]
            ) or len(markers) - 1 > MAX_COMPLETE_OWNERS):
        _refuse("legacy header owner and issuer topology is ambiguous")
    owners = [
        _legacy_role_cik(roles[start + 1:markers[index + 1][0]], owner=True, target=target)
        for index, (start, _) in enumerate(markers[:-1])
    ]
    issuer = _legacy_role_cik(roles[markers[-1][0] + 1:], owner=False, target=target)
    if issuer != target.issuer_cik or len(set(owners)) != len(owners):
        _refuse("legacy header issuer or owner identity disagrees with target")
    return {
        "accepted_at_raw": accepted, "owner_ciks": owners,
        "public_document_count": int(preamble["PUBLIC DOCUMENT COUNT"]),
    }


def _header_identity(raw: bytes, target: SecCompleteSubmissionTarget) -> dict[str, object]:
    if not 0 < len(raw) <= MAX_COMPLETE_HEADER_BYTES:
        _refuse("header exceeds its exact byte cap")
    if any(byte < 32 and byte not in (9, 10, 13) for byte in raw):
        _refuse("header has unsupported control bytes")
    try:
        text = raw.decode("ascii", errors="strict").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise SecCompleteSubmissionError("REFUSED: header is not strict ASCII") from exc
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    if len(lines) < 9 or lines[-1] != "</SEC-HEADER>":
        _refuse("header envelope is incomplete")
    opener = re.fullmatch(
        r"<SEC-HEADER>([0-9]{10}-[0-9]{2}-[0-9]{6})\.hdr\.sgml : ([0-9]{8})",
        lines[0],
    )
    if opener is None or opener.group(1) != target.accession_number:
        _refuse("header opener disagrees with accession")
    _date_digits(opener.group(2).encode("ascii"), label="header opener date")
    body = lines[1:-1]
    if len(body) > 1 and body[1].startswith("ACCESSION NUMBER:"):
        return _legacy_header_identity(body, target)
    markers = [(index, line) for index, line in enumerate(body) if line in _ROOT_MARKERS]
    if (not markers or sum(line.count(marker) for line in body for marker in _ROOT_MARKERS)
            != len(markers)):
        _refuse("header root roles are disguised or nested")
    ordered = [marker for _, marker in markers]
    owner_count = (len(ordered) - 2) // 2
    if (not 1 <= owner_count <= MAX_COMPLETE_OWNERS
            or ordered != ["<REPORTING-OWNER>", "</REPORTING-OWNER>"] * owner_count
            + ["<ISSUER>", "</ISSUER>"]):
        _refuse("header owner and issuer topology is ambiguous")
    if markers[-1][0] != len(body) - 1:
        _refuse("header has content after issuer")
    preamble = body[:markers[0][0]]
    seen: set[str] = set()
    for line in preamble:
        match = _TAG_FIELD.fullmatch(line)
        if match is None or match.group(1) not in _HEADER_PREAMBLE or match.group(1) in seen:
            _refuse("header preamble has a foreign, malformed, or repeated field")
        seen.add(match.group(1))
    required = ("ACCESSION-NUMBER", "TYPE", "FILING-DATE", "ACCEPTANCE-DATETIME")
    fields = {name: _unique_tag(preamble, name, label="header") for name in required}
    if any(sum(line.startswith(f"<{name}>") for line in body) != 1 for name in required):
        _refuse("header identity appears outside its preamble")
    if (fields["ACCESSION-NUMBER"] != target.accession_number
            or fields["TYPE"] != target.form_type
            or fields["FILING-DATE"] != target.filing_date.replace("-", "")):
        _refuse("header accession, form, or filing date disagrees with target")
    accepted = fields["ACCEPTANCE-DATETIME"]
    if re.fullmatch(r"[0-9]{14}", accepted) is None:
        _refuse("acceptance timestamp is not fourteen digits")
    _date_digits(accepted[:8].encode("ascii"), label="acceptance date")
    try:
        datetime.strptime(accepted, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise SecCompleteSubmissionError("REFUSED: acceptance time is invalid") from exc
    owners: list[str] = []
    try:
        for index in range(owner_count):
            opening = markers[2 * index][0]
            closing = markers[2 * index + 1][0]
            if closing <= opening + 1:
                _refuse("reporting-owner role is empty")
            owners.append(_cik(_company_cik(body[opening + 1:closing], outer="owner"),
                               label="owner CIK"))
        issuer_open, issuer_close = markers[-2][0], markers[-1][0]
        issuer = _cik(_company_cik(body[issuer_open + 1:issuer_close], outer="issuer"),
                      label="issuer CIK")
    except SecRawParentProjectionError as exc:
        raise SecCompleteSubmissionError(str(exc)) from exc
    if issuer != target.issuer_cik:
        _refuse("header issuer CIK disagrees with target")
    if len(set(owners)) != len(owners):
        _refuse("header repeats a reporting owner")
    if any(markers[2 * index + 2][0] != markers[2 * index + 1][0] + 1
           for index in range(owner_count - 1)):
        _refuse("header has content between reporting owners")
    if issuer_open != markers[-3][0] + 1:
        _refuse("header has content between owners and issuer")
    return {"accepted_at_raw": accepted, "owner_ciks": owners}


def _document(raw_lines: list[bytes], pieces: list[bytes],
              start: int) -> tuple[int, str, str, bytes]:
    if raw_lines[start] != b"<DOCUMENT>":
        _refuse("unexpected material outside a DOCUMENT")
    try:
        end = raw_lines.index(b"</DOCUMENT>", start + 1)
    except ValueError as exc:
        raise SecCompleteSubmissionError("REFUSED: DOCUMENT is incomplete") from exc
    if b"<DOCUMENT>" in raw_lines[start + 1:end]:
        _refuse("nested DOCUMENT is unsupported")
    try:
        text_start = raw_lines.index(b"<TEXT>", start + 1, end)
        text_end = raw_lines.index(b"</TEXT>", text_start + 1, end)
    except ValueError as exc:
        raise SecCompleteSubmissionError("REFUSED: TEXT scope is incomplete") from exc
    if (b"<TEXT>" in raw_lines[text_start + 1:end]
            or b"</TEXT>" in raw_lines[text_end + 1:end]
            or text_end != end - 1):
        _refuse("TEXT scope is ambiguous or has trailing material")
    metadata: dict[str, str] = {}
    for line in raw_lines[start + 1:text_start]:
        try:
            value = line.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise SecCompleteSubmissionError("REFUSED: document header is not ASCII") from exc
        match = _TAG_FIELD.fullmatch(value)
        if (match is None or match.group(1) not in {"TYPE", "SEQUENCE", "FILENAME", "DESCRIPTION"}
                or match.group(1) in metadata):
            _refuse("document header is malformed or ambiguous")
        metadata[match.group(1)] = match.group(2)
    # Superset test: a proper-subset comparison let a header carrying
    # DESCRIPTION but lacking a required field escape as KeyError.
    if not {"TYPE", "SEQUENCE", "FILENAME"} <= set(metadata):
        _refuse("document header lacks type, sequence, or filename")
    if re.fullmatch(r"[1-9][0-9]{0,5}", metadata["SEQUENCE"]) is None:
        _refuse("document sequence is invalid")
    filename = metadata["FILENAME"]
    if _NAME.fullmatch(filename) is None or ".." in filename:
        _refuse("document filename is unsafe")
    body_start, body_end = text_start + 1, text_end
    if (body_start < body_end and raw_lines[body_start] == b"<XML>"
            and raw_lines[body_end - 1] == b"</XML>"):
        body_start += 1
        body_end -= 1
    if (body_start >= body_end
            or b"<XML>" in raw_lines[body_start:body_end]
            or b"</XML>" in raw_lines[body_start:body_end]
            or any(line in {b"<DOCUMENT>", b"</DOCUMENT>", b"<TEXT>", b"</TEXT>"}
                   for line in raw_lines[body_start:body_end])):
        _refuse("document text or XML wrapper is incomplete or nested")
    return end + 1, metadata["TYPE"], filename, b"".join(pieces[body_start:body_end])


def _extract(target: SecCompleteSubmissionTarget, raw: bytes) -> tuple[bytes, bytes, str, str, tuple[str, ...]]:
    pieces, lines = _split_lines(raw)
    opener = re.fullmatch(
        rb"<SEC-DOCUMENT>([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt : ([0-9]{8})",
        lines[0],
    )
    if (opener is None or opener.group(1).decode("ascii") != target.accession_number
            or lines[-1] != b"</SEC-DOCUMENT>"
            or raw.count(b"<SEC-DOCUMENT>") != 1
            or raw.count(b"</SEC-DOCUMENT>") != 1):
        _refuse("SEC-DOCUMENT envelope disagrees with target or is incomplete")
    _date_digits(opener.group(2), label="SEC-DOCUMENT opener date")
    if len(lines) < 4 or not lines[1].startswith(b"<SEC-HEADER>"):
        _refuse("complete submission has no leading SEC-HEADER")
    try:
        header_end = lines.index(b"</SEC-HEADER>", 2, len(lines) - 1)
    except ValueError as exc:
        raise SecCompleteSubmissionError("REFUSED: SEC-HEADER is incomplete") from exc
    if (sum(line.startswith(b"<SEC-HEADER>") for line in lines) != 1
            or lines.count(b"</SEC-HEADER>") != 1):
        _refuse("SEC-HEADER is duplicated or nested")
    header = b"".join(pieces[1:header_end + 1])
    header_fields = _header_identity(header, target)
    position = header_end + 1
    documents = 0
    seen_sequences: set[str] = set()
    xml_docs: list[tuple[str, str, bytes]] = []
    while position < len(lines) - 1:
        if documents >= MAX_COMPLETE_DOCUMENTS:
            _refuse("complete submission has too many documents")
        next_position, form, filename, body = _document(lines, pieces, position)
        documents += 1
        # Sequence uniqueness is checked from the exact document metadata by
        # scanning its bounded header, not inferred from document order.
        metadata_lines = lines[position + 1:lines.index(b"<TEXT>", position + 1, next_position)]
        sequence = next(line.removeprefix(b"<SEQUENCE>").decode("ascii")
                        for line in metadata_lines if line.startswith(b"<SEQUENCE>"))
        if sequence in seen_sequences:
            _refuse("document sequence is duplicated")
        seen_sequences.add(sequence)
        if filename.casefold().endswith(".xml"):
            if (_XML_NAME.fullmatch(filename) is None
                    or filename.casefold().startswith("xsl")):
                _refuse("ownership XML filename is unsafe")
            xml_docs.append((form, filename, body))
        position = next_position
    if ("public_document_count" in header_fields
            and header_fields["public_document_count"] != documents):
        _refuse("legacy header document count disagrees with complete submission")
    if documents == 0 or len(xml_docs) != 1:
        _refuse("exactly one ownership XML document is required")
    form, filename, xml = xml_docs[0]
    if form != target.form_type or not 0 < len(xml) <= MAX_COMPLETE_XML_BYTES:
        _refuse("primary XML type or byte size disagrees with target")
    try:
        xml_fields = _xml_fields(xml, target)  # Same strict XML identity guard as the pilot.
    except SecRawParentProjectionError as exc:
        raise SecCompleteSubmissionError(str(exc)) from exc
    if set(header_fields["owner_ciks"]) != set(xml_fields["xml_owner_ciks_normalized"]):
        _refuse("header and XML reporting-owner identities disagree")
    return (header, xml, filename, str(header_fields["accepted_at_raw"]),
            tuple(header_fields["owner_ciks"]))


def _authority() -> dict[str, object]:
    return {
        "source_authenticated": False,
        "index_membership_verified": False,
        "real_shape_verified": False,
        "official_header_profile_verified": False,
        "timezone_interpretation_verified": False,
        "point_in_time_data": False,
        "canonical_evidence": False,
        "direct_ib1c_ingest_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }


@dataclass(frozen=True)
class SecCompleteSubmissionProjection:
    target: SecCompleteSubmissionTarget
    raw_bytes: bytes
    header_bytes: bytes = field(init=False)
    xml_bytes: bytes = field(init=False)
    primary_xml_filename: str = field(init=False)
    accepted_at_raw: str = field(init=False)
    header_owner_ciks: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        if type(self) is not SecCompleteSubmissionProjection:
            _refuse("an exact complete-submission projection is required")
        object.__setattr__(self, "target", _copy_target(self.target))
        header, xml, filename, accepted, owners = _extract(self.target, self.raw_bytes)
        object.__setattr__(self, "header_bytes", header)
        object.__setattr__(self, "xml_bytes", xml)
        object.__setattr__(self, "primary_xml_filename", filename)
        object.__setattr__(self, "accepted_at_raw", accepted)
        object.__setattr__(self, "header_owner_ciks", owners)

    def to_payload(self) -> dict[str, object]:
        if type(self) is not SecCompleteSubmissionProjection:
            _refuse("an exact complete-submission projection is required")
        target = _copy_target(self.target)
        header, xml, filename, accepted, owners = _extract(target, self.raw_bytes)
        if (header != self.header_bytes or xml != self.xml_bytes
                or filename != self.primary_xml_filename
                or accepted != self.accepted_at_raw
                or owners != self.header_owner_ciks):
            _refuse("derived children were altered after construction")
        parent_sha = hash_bytes(self.raw_bytes)
        return {
            "version": SEC_COMPLETE_SUBMISSION_VERSION,
            "target": target.to_payload(),
            "raw_parent": {
                "declared_complete_submission_url": target.complete_submission_url,
                "declared_quarterly_index_sha256": target.quarterly_index_sha256,
                "sha256": parent_sha,
                "size_bytes": len(self.raw_bytes),
            },
            "children": {
                "header": {
                    "parent_sha256": parent_sha,
                    "sha256": hash_bytes(header),
                    "size_bytes": len(header),
                },
                "primary_xml": {
                    "parent_sha256": parent_sha,
                    "filename": filename,
                    "sha256": hash_bytes(xml),
                    "size_bytes": len(xml),
                },
            },
            "source_fields": {
                "accepted_at_raw": accepted,
                "header_owner_ciks": list(owners),
            },
            "authority": _authority(),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def project_sec_complete_submission(
    target: SecCompleteSubmissionTarget, complete_submission_bytes: bytes,
) -> SecCompleteSubmissionProjection:
    """Parse a supplied image without fetching, persisting, or promoting it."""
    return SecCompleteSubmissionProjection(target, complete_submission_bytes)
