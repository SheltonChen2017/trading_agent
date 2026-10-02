"""Frozen, noncanonical IB-1B preparation profile for two owner-selected quarters.

These vectors were observed from only the first physical TSV header lines in
the owner-supplied 2022Q4 and 2023Q1 ZIPs. They are not a general SEC registry,
an authenticated retrieval receipt, or authority to process data. This module
does no I/O and does not inspect rows or imply their keys are empirically unique.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
)


PILOT_PERIODS = ((2022, 4), (2023, 1))
PILOT_SCHEMA_PROFILE_SHA256 = "54abe3073a83b4da9231aaa62b58b50907af2a6815f721890312b0f6c8a41f2e"
PILOT_ARCHIVE_BINDINGS_SHA256 = "3ac52c110a641acf3c9420c2e32877d4a624cec73fcf041b5ba2a90047ad8f6f"
PILOT_TIMESTAMP_BASIS = "local filesystem last-write time; not SEC-attested"
_CAPTURE_COMMIT = "a4192546b168470ff1e9c421d8bd53531a1b3c05"
_SOURCE_PREFIX = (
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_LOCAL_STAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{7}Z")
_HEADER_RE = re.compile(r"[A-Z][A-Z0-9_]*")

# Tuple order is IB-1A's canonical table order. SEC spelling is preserved.
_HEADERS_BY_TABLE = (
    ("SUBMISSION.tsv", tuple((
        "ACCESSION_NUMBER FILING_DATE PERIOD_OF_REPORT DATE_OF_ORIG_SUB "
        "NO_SECURITIES_OWNED NOT_SUBJECT_SEC16 FORM3_HOLDINGS_REPORTED "
        "FORM4_TRANS_REPORTED DOCUMENT_TYPE ISSUERCIK ISSUERNAME "
        "ISSUERTRADINGSYMBOL REMARKS"
    ).split())),
    ("REPORTINGOWNER.tsv", tuple((
        "ACCESSION_NUMBER RPTOWNERCIK RPTOWNERNAME RPTOWNER_RELATIONSHIP "
        "RPTOWNER_TITLE RPTOWNER_TXT RPTOWNER_STREET1 RPTOWNER_STREET2 "
        "RPTOWNER_CITY RPTOWNER_STATE RPTOWNER_ZIPCODE RPTOWNER_STATE_DESC FILE_NUMBER"
    ).split())),
    ("NONDERIV_TRANS.tsv", tuple((
        "ACCESSION_NUMBER NONDERIV_TRANS_SK SECURITY_TITLE SECURITY_TITLE_FN "
        "TRANS_DATE TRANS_DATE_FN DEEMED_EXECUTION_DATE DEEMED_EXECUTION_DATE_FN "
        "TRANS_FORM_TYPE TRANS_CODE EQUITY_SWAP_INVOLVED EQUITY_SWAP_TRANS_CD_FN "
        "TRANS_TIMELINESS TRANS_TIMELINESS_FN TRANS_SHARES TRANS_SHARES_FN "
        "TRANS_PRICEPERSHARE TRANS_PRICEPERSHARE_FN TRANS_ACQUIRED_DISP_CD "
        "TRANS_ACQUIRED_DISP_CD_FN SHRS_OWND_FOLWNG_TRANS SHRS_OWND_FOLWNG_TRANS_FN "
        "VALU_OWND_FOLWNG_TRANS VALU_OWND_FOLWNG_TRANS_FN DIRECT_INDIRECT_OWNERSHIP "
        "DIRECT_INDIRECT_OWNERSHIP_FN NATURE_OF_OWNERSHIP NATURE_OF_OWNERSHIP_FN"
    ).split())),
    ("NONDERIV_HOLDING.tsv", tuple((
        "ACCESSION_NUMBER NONDERIV_HOLDING_SK SECURITY_TITLE SECURITY_TITLE_FN "
        "TRANS_FORM_TYPE TRANS_FORM_TYPE_FN SHRS_OWND_FOLWNG_TRANS "
        "SHRS_OWND_FOLWNG_TRANS_FN VALU_OWND_FOLWNG_TRANS VALU_OWND_FOLWNG_TRANS_FN "
        "DIRECT_INDIRECT_OWNERSHIP DIRECT_INDIRECT_OWNERSHIP_FN "
        "NATURE_OF_OWNERSHIP NATURE_OF_OWNERSHIP_FN"
    ).split())),
    ("DERIV_TRANS.tsv", tuple((
        "ACCESSION_NUMBER DERIV_TRANS_SK SECURITY_TITLE SECURITY_TITLE_FN "
        "CONV_EXERCISE_PRICE CONV_EXERCISE_PRICE_FN TRANS_DATE TRANS_DATE_FN "
        "DEEMED_EXECUTION_DATE DEEMED_EXECUTION_DATE_FN TRANS_FORM_TYPE TRANS_CODE "
        "EQUITY_SWAP_INVOLVED EQUITY_SWAP_TRANS_CD_FN TRANS_TIMELINESS "
        "TRANS_TIMELINESS_FN TRANS_SHARES TRANS_SHARES_FN TRANS_TOTAL_VALUE "
        "TRANS_TOTAL_VALUE_FN TRANS_PRICEPERSHARE TRANS_PRICEPERSHARE_FN "
        "TRANS_ACQUIRED_DISP_CD TRANS_ACQUIRED_DISP_CD_FN EXCERCISE_DATE "
        "EXCERCISE_DATE_FN EXPIRATION_DATE EXPIRATION_DATE_FN UNDLYNG_SEC_TITLE "
        "UNDLYNG_SEC_TITLE_FN UNDLYNG_SEC_SHARES UNDLYNG_SEC_SHARES_FN "
        "UNDLYNG_SEC_VALUE UNDLYNG_SEC_VALUE_FN SHRS_OWND_FOLWNG_TRANS "
        "SHRS_OWND_FOLWNG_TRANS_FN VALU_OWND_FOLWNG_TRANS VALU_OWND_FOLWNG_TRANS_FN "
        "DIRECT_INDIRECT_OWNERSHIP DIRECT_INDIRECT_OWNERSHIP_FN "
        "NATURE_OF_OWNERSHIP NATURE_OF_OWNERSHIP_FN"
    ).split())),
    ("DERIV_HOLDING.tsv", tuple((
        "ACCESSION_NUMBER DERIV_HOLDING_SK SECURITY_TITLE SECURITY_TITLE_FN "
        "CONV_EXERCISE_PRICE CONV_EXERCISE_PRICE_FN TRANS_FORM_TYPE TRANS_FORM_TYPE_FN "
        "EXERCISE_DATE EXERCISE_DATE_FN EXPIRATION_DATE EXPIRATION_DATE_FN "
        "UNDLYNG_SEC_TITLE UNDLYNG_SEC_TITLE_FN UNDLYNG_SEC_SHARES UNDLYNG_SEC_SHARES_FN "
        "UNDLYNG_SEC_VALUE UNDLYNG_SEC_VALUE_FN SHRS_OWND_FOLWNG_TRANS "
        "SHRS_OWND_FOLWNG_TRANS_FN VALU_OWND_FOLWNG_TRANS VALU_OWND_FOLWNG_TRANS_FN "
        "DIRECT_INDIRECT_OWNERSHIP DIRECT_INDIRECT_OWNERSHIP_FN "
        "NATURE_OF_OWNERSHIP NATURE_OF_OWNERSHIP_FN"
    ).split())),
    ("FOOTNOTES.tsv", ("ACCESSION_NUMBER", "FOOTNOTE_ID", "FOOTNOTE_TXT")),
    ("OWNER_SIGNATURE.tsv", ("ACCESSION_NUMBER", "OWNERSIGNATURENAME", "OWNERSIGNATUREDATE")),
)
_HEADER_LINES = (
    ("SUBMISSION.tsv", 209, "7500cd2ad9bac8264c6b1397eef0ba6141ea0738403a914f0d4e74657f92086d"),
    ("REPORTINGOWNER.tsv", 204, "4b712596920a4e3b5a504c18ab233c858d9f3d701c5ddd3393a11b2c7854c4b7"),
    ("NONDERIV_TRANS.tsv", 566, "26483a4ee2354b1a5ccc663eb3185d08a10c17f172b541dd6e0a55d4c216c290"),
    ("NONDERIV_HOLDING.tsv", 301, "c1e6af74144f525da37766116a2ade6b045bb53d39f016cdabe1ba6942b54474"),
    ("DERIV_TRANS.tsv", 832, "0f8d910f6f5e29851f07126d2bfaaaa9ba5efedd14841a80868409cf667dd6b1"),
    ("DERIV_HOLDING.tsv", 526, "c77b4c43ad560d5b44c474149522be592fd3e3c8bf85c91579db95cc57b39784"),
    ("FOOTNOTES.tsv", 42, "4be9ffe6da5173b50125082dac0890f87bc25f2150010d06bbb7532604281aeb"),
    ("OWNER_SIGNATURE.tsv", 55, "dd9b7eb67a150e5244d4d46db94f15006301bc91cd0676d888879f08ce0eae73"),
)
_ARCHIVES = (
    (2022, 4, "2022q4_form345.zip", 8400983, "6c6a909bd2eaaa0a24ccf5f0071b404670c115845d2939bc592bf3ce420dcdb9", "2026-09-24T22:53:37.3844487Z", (4129394, 6118412, 6545081, 1504590, 3441608, 1186565, 25477724, 3435663)),
    (2023, 1, "2023q1_form345.zip", 13882049, "0b476188f52a0862e71886eb31a81f6345fc6616403b52188484aef0438cfcfb", "2026-09-24T22:53:38.4646512Z", (7256966, 10548221, 11612126, 2607621, 6909690, 2175215, 43908088, 5788549)),
)


class Ib1bPilotProfileError(ValueError):
    """The exact reviewed pilot preparation contract failed closed."""


def _variant(
    table: str,
    headers: tuple[str, ...],
    start: tuple[int, int],
    end: tuple[int, int],
) -> SecTsvSchemaVariant:
    key = {
        "NONDERIV_TRANS.tsv": ("NONDERIV_TRANS_SK",),
        "DERIV_TRANS.tsv": ("DERIV_TRANS_SK",),
    }.get(table, ())
    return SecTsvSchemaVariant(
        schema_id=f"IB1B-pilot-{table.removesuffix('.tsv')}-{start[0]}Q{start[1]}-{end[0]}Q{end[1]}-v1",
        table_name=table,
        headers=headers,
        source_row_key_headers=key,
        valid_from_year=start[0],
        valid_from_quarter=start[1],
        valid_through_year=end[0],
        valid_through_quarter=end[1],
    )


def verify_approved_ib1b_schema_profile(profile: object) -> None:
    """Check exact nested types and the independently frozen profile digest."""
    if type(profile) is not SecTsvSchemaProfile or type(profile.variants) is not tuple:
        raise Ib1bPilotProfileError("REFUSED: pilot schema profile types are not exact")
    if type(profile.profile_id) is not str:
        raise Ib1bPilotProfileError("REFUSED: pilot schema profile types are not exact")
    for variant in profile.variants:
        if type(variant) is not SecTsvSchemaVariant:
            raise Ib1bPilotProfileError("REFUSED: pilot schema profile types are not exact")
        if any(
            type(value) is not str
            for value in (variant.schema_id, variant.table_name)
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot schema profile types are not exact")
        if any(
            type(value) is not int
            for value in (
                variant.valid_from_year, variant.valid_from_quarter,
                variant.valid_through_year, variant.valid_through_quarter,
            )
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot schema profile types are not exact")
        for vector in (variant.headers, variant.source_row_key_headers):
            if type(vector) is not tuple or any(
                type(value) is not str for value in vector
            ):
                raise Ib1bPilotProfileError("REFUSED: pilot schema profile types are not exact")
    if hash_payload(profile.to_payload()) != PILOT_SCHEMA_PROFILE_SHA256:
        raise Ib1bPilotProfileError("REFUSED: pilot schema profile fingerprint mismatch")


def _profile() -> SecTsvSchemaProfile:
    variants = []
    for table, headers in _HEADERS_BY_TABLE:
        if table == "SUBMISSION.tsv":
            variants.append(_variant(table, headers, (2022, 4), (2022, 4)))
            variants.append(_variant(table, headers + ("AFF10B5ONE",), (2023, 1), (2023, 1)))
        else:
            variants.append(_variant(table, headers, (2022, 4), (2023, 1)))
    return SecTsvSchemaProfile("IB1B-pilot-2022Q4-2023Q1-observed-headers-v1", tuple(variants))


def approved_ib1b_schema_profile() -> SecTsvSchemaProfile:
    """Return a fresh, exact profile; this does not authorize running a pilot."""
    profile = _profile()
    verify_approved_ib1b_schema_profile(profile)
    return profile


@dataclass(frozen=True)
class PilotHeaderReceipt:
    table_name: str
    headers: tuple[str, ...]
    header_line_sha256: str
    header_line_size_bytes: int
    expanded_size_bytes: int

    def __post_init__(self) -> None:
        if (
            any(type(value) is not str for value in (self.table_name, self.header_line_sha256))
            or type(self.headers) is not tuple
            or any(type(value) is not str for value in self.headers)
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot header receipt types are not exact")
        if (
            type(self.header_line_size_bytes) is not int
            or type(self.expanded_size_bytes) is not int
            or self.expanded_size_bytes < self.header_line_size_bytes
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot header receipt sizes are invalid")
        if (
            self.table_name not in {item[0] for item in _HEADERS_BY_TABLE}
            or not self.headers
            or any(_HEADER_RE.fullmatch(value) is None for value in self.headers)
            or _SHA256_RE.fullmatch(self.header_line_sha256) is None
            or self.header_line_size_bytes <= 0
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot header receipt fields are invalid")
        line = ("\t".join(self.headers) + "\n").encode("ascii")
        if len(line) != self.header_line_size_bytes or hash_bytes(line) != self.header_line_sha256:
            raise Ib1bPilotProfileError("REFUSED: pilot header receipt fingerprint mismatch")

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "headers": list(self.headers),
            "header_line_sha256": self.header_line_sha256,
            "header_line_size_bytes": self.header_line_size_bytes,
            "expanded_size_bytes": self.expanded_size_bytes,
        }


@dataclass(frozen=True)
class PilotArchiveBinding:
    year: int
    quarter: int
    filename: str
    archive_sha256: str
    archive_size_bytes: int
    source_url: str
    capture_git_commit: str
    local_last_write_utc: str
    timestamp_basis: str
    source_provenance_verified: bool
    header_receipts: tuple[PilotHeaderReceipt, ...]

    def __post_init__(self) -> None:
        if (
            any(type(value) is not int for value in (self.year, self.quarter, self.archive_size_bytes))
            or any(
                type(value) is not str
                for value in (
                    self.filename, self.archive_sha256, self.source_url,
                    self.capture_git_commit, self.local_last_write_utc,
                    self.timestamp_basis,
                )
            )
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot archive binding types are not exact")
        if (
            type(self.source_provenance_verified) is not bool
            or self.source_provenance_verified is not False
            or self.timestamp_basis != PILOT_TIMESTAMP_BASIS
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot source provenance is unverified")
        if (
            (self.year, self.quarter) not in PILOT_PERIODS
            or self.archive_size_bytes <= 0
            or self.filename != f"{self.year}q{self.quarter}_form345.zip"
            or self.source_url != _SOURCE_PREFIX + self.filename
            or _SHA256_RE.fullmatch(self.archive_sha256) is None
            or _GIT_COMMIT_RE.fullmatch(self.capture_git_commit) is None
            or _LOCAL_STAMP_RE.fullmatch(self.local_last_write_utc) is None
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot archive binding fields are invalid")
        if (
            type(self.header_receipts) is not tuple
            or len(self.header_receipts) != 8
            or any(type(item) is not PilotHeaderReceipt for item in self.header_receipts)
        ):
            raise Ib1bPilotProfileError("REFUSED: pilot header receipt types are not exact")
        for item in self.header_receipts:
            item.__post_init__()

    def to_payload(self) -> dict[str, object]:
        return {
            "year": self.year, "quarter": self.quarter,
            "filename": self.filename, "archive_sha256": self.archive_sha256,
            "archive_size_bytes": self.archive_size_bytes, "source_url": self.source_url,
            "capture_git_commit": self.capture_git_commit,
            "local_last_write_utc": self.local_last_write_utc,
            "timestamp_basis": self.timestamp_basis,
            "source_provenance_verified": self.source_provenance_verified,
            "header_receipts": [item.to_payload() for item in self.header_receipts],
        }


def _bindings() -> tuple[PilotArchiveBinding, ...]:
    profile = approved_ib1b_schema_profile()
    bindings = []
    for year, quarter, filename, size, digest, stamp, expanded_sizes in _ARCHIVES:
        receipts = []
        for (table, line_size, line_digest), expanded_size in zip(
            _HEADER_LINES, expanded_sizes, strict=True
        ):
            if table == "SUBMISSION.tsv" and (year, quarter) == (2023, 1):
                line_size = 220
                line_digest = "fc8c3f66d6e259fb7826fbe46cee2d6baaff49786f9b7c6a400c092f9b67cc6d"
            receipts.append(PilotHeaderReceipt(
                table, profile.variant_for(table, year, quarter).headers,
                line_digest, line_size, expanded_size,
            ))
        bindings.append(PilotArchiveBinding(
            year, quarter, filename, digest, size, _SOURCE_PREFIX + filename,
            _CAPTURE_COMMIT, stamp, PILOT_TIMESTAMP_BASIS, False, tuple(receipts),
        ))
    return tuple(bindings)


def verify_approved_ib1b_archive_bindings(bindings: object) -> None:
    """Refuse structurally or semantically altered source/header declarations."""
    if (
        type(bindings) is not tuple
        or len(bindings) != 2
        or any(type(item) is not PilotArchiveBinding for item in bindings)
    ):
        raise Ib1bPilotProfileError("REFUSED: pilot archive binding types are not exact")
    for item in bindings:
        item.__post_init__()
    if hash_payload([item.to_payload() for item in bindings]) != PILOT_ARCHIVE_BINDINGS_SHA256:
        raise Ib1bPilotProfileError("REFUSED: pilot archive binding fingerprint mismatch")


def approved_ib1b_archive_bindings() -> tuple[PilotArchiveBinding, ...]:
    """Return fresh receipts for the two supplied ZIPs, not authenticated provenance."""
    bindings = _bindings()
    verify_approved_ib1b_archive_bindings(bindings)
    return bindings
