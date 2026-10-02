"""Read-only, noncanonical projection of the exact retained 16-filing SEC pilot.

The public entry point is pinned to one already-acquired continuation report.
It neither fetches SEC bytes nor publishes an artifact. A matching local hash
binds supplied bytes, not SEC authenticity, PIT status, or IB-1C authority.
The attempts journal is required as part of the publication layout but is not
replayed or attested by this projection adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying.sec_acquisition_preparation import (
    SecAcquisitionPreparationError,
    SecAcquisitionTarget,
)
from research.insider_buying.sec_bulk_snapshot import (
    SecBulkSnapshotError,
    _read_regular_bytes,
    _require_regular_directory,
)
from research.insider_buying.sec_raw_parent_projection import (
    SecRawParentProjection,
    SecRawParentProjectionError,
    derive_sec_raw_parent_projection,
)


OFFLINE_PILOT_ADAPTER_VERSION = "INSETF-SEC-SIXTEEN-OFFLINE-PROJECTION-v1"
FINAL_REPORT_SHA256 = "722ab1b03c93d1d6aa61f798b2cb6a391a934ee8a334034eff2b5102cea40ec5"
INVENTORY_SHA256 = "4b8a4c3a233855ea2aa6cde0b2739a83aca478180ac881e1cf011943753d78db"
FIRST_PASS_REPORT_SHA256 = "410bbb079f9cec25733e798d3aceaea179c0d47d657743d199a041922d81f642"
FIRST_PASS_JOURNAL_SHA256 = "e56ec3fb369a11598bb2ac30cf5fd1f1e299c52fae1a6ee410c6816c4d2586db"
FIRST_PASS_CODE_COMMIT = "f5430fff9b09a963b5cb0307c9e87b28a69c4767"
CONTINUATION_CODE_COMMIT = "5cc897dbf9b7e9216370b2157ef79c9c9b2a0508"
_PILOT_VERSION = "INSETF-SEC-SIXTEEN-ACQUISITION-v1"
_CONTINUATION_VERSION = "INSETF-SEC-SIXTEEN-XML-CONTINUATION-v1"
_INDEX_ROUTE_VERSION = "sec-accession-directory-index-json-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CANDIDATE_KEYS = frozenset({
    "period", "accession_number", "form_type", "filing_date_raw",
    "filing_date", "issuer_cik", "quarterly_zip_sha256", "submission_row_id",
    "raw_snapshot_id", "raw_lineage_sha256",
})
_REPORT_KEYS = frozenset({
    "kind", "canonical", "point_in_time_data", "direct_ib1c_ingest_authorized",
    "source_authenticity_verified", "official_sec_profile_verified",
    "timezone_interpretation_verified", "research_looks", "authorized_outcome_looks",
    "consumed_outcome_looks", "inventory_sha256", "index_route_version",
    "first_pass_report_sha256", "first_pass_journal_sha256",
    "first_pass_code_commit_operator_attested", "prior_code_sha_artifact_verified",
    "continuation_code_commit_verified", "cumulative_attempt_count",
    "cumulative_distinct_artifact_count", "new_attempt_count",
    "halted_on_sec_access", "rows", "acquisition_available",
})
_ROW_KEYS = frozenset({
    "candidate", "primary_xml_filename", "status", "reason", "first_pass_reason",
    "artifacts", "tag_header_validation",
})
FIXED_ACCESSIONS = (
    "0000002178-22-000091", "0000002178-22-000094", "0000002178-22-000095",
    "0000002178-22-000097", "0000002178-22-000099", "0000002488-22-000165",
    "0000050725-22-000079", "0000050725-22-000083",
    "0000002178-23-000019", "0000002178-23-000020", "0000002178-23-000021",
    "0000002178-23-000022", "0000002178-23-000023", "0000002178-23-000024",
    "0000016058-23-000011", "0000019745-23-000002",
)
_LOADER_TOKEN = object()


class SecOfflinePilotAdapterError(ValueError):
    """The exact retained pilot receipt or a raw parent failed closed."""


def _refuse(message: str) -> None:
    raise SecOfflinePilotAdapterError(f"REFUSED: {message}")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _refuse("receipt repeats a JSON key")
        result[key] = value
    return result


def _non_json_constant(_: str) -> object:
    _refuse("receipt contains a non-JSON constant")


def _canonical_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_pairs,
            parse_constant=_non_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SecOfflinePilotAdapterError(f"REFUSED: {label} is not strict JSON") from exc
    if type(value) is not dict or (canonical_json(value) + "\n").encode("utf-8") != raw:
        _refuse(f"{label} is not canonical JSON plus one LF")
    return value


def _plain_root(value: str | Path) -> Path:
    if type(value) is not str and not isinstance(value, Path):
        _refuse("root must be an exact absolute path")
    root = Path(value)
    if not root.is_absolute() or ".." in root.parts:
        _refuse("root must be absolute and non-traversing")
    try:
        for component in (*reversed(root.parents), root):
            _require_regular_directory(component, label="pilot root or ancestor")
    except SecBulkSnapshotError as exc:
        raise SecOfflinePilotAdapterError(str(exc)) from exc
    return root


def _names(root: Path, *, label: str) -> set[str]:
    try:
        names = [item.name for item in root.iterdir()]
    except OSError as exc:
        raise SecOfflinePilotAdapterError(f"REFUSED: {label} cannot be enumerated") from exc
    if len(names) != len(set(names)):
        _refuse(f"{label} repeats a name")
    return set(names)


def _read(root: Path, name: str, *, label: str, max_bytes: int) -> bytes:
    try:
        return _read_regular_bytes(
            root / name, label=label, max_bytes=max_bytes, require_single_link=True,
        )
    except SecBulkSnapshotError as exc:
        raise SecOfflinePilotAdapterError(str(exc)) from exc


def _descriptor(root: Path, descriptor: object, *, role: str) -> bytes:
    if (type(descriptor) is not dict
            or set(descriptor) != {"relative_path", "sha256", "size_bytes"}
            or type(descriptor["sha256"]) is not str
            or _SHA.fullmatch(descriptor["sha256"]) is None
            or type(descriptor["size_bytes"]) is not int
            or not 0 < descriptor["size_bytes"] <= 2 * 1024 * 1024
            or descriptor["relative_path"] != f'objects/{descriptor["sha256"]}.bin'):
        _refuse(f"{role} has an unsafe content-addressed descriptor")
    raw = _read(root, descriptor["relative_path"], label=f"pilot {role}",
                max_bytes=2 * 1024 * 1024)
    if len(raw) != descriptor["size_bytes"] or hash_bytes(raw) != descriptor["sha256"]:
        _refuse(f"{role} byte size or SHA-256 disagrees with receipt")
    return raw


def _checked_report(report: dict[str, object], *, inventory_sha256: str) -> list[object]:
    if set(report) != _REPORT_KEYS:
        _refuse("continuation report schema drifted")
    fixed = {
        "kind": _CONTINUATION_VERSION,
        "inventory_sha256": inventory_sha256,
        "index_route_version": _INDEX_ROUTE_VERSION,
        "first_pass_report_sha256": FIRST_PASS_REPORT_SHA256,
        "first_pass_journal_sha256": FIRST_PASS_JOURNAL_SHA256,
        "first_pass_code_commit_operator_attested": FIRST_PASS_CODE_COMMIT,
        "continuation_code_commit_verified": CONTINUATION_CODE_COMMIT,
    }
    if any(type(report[key]) is not str or report[key] != value
           for key, value in fixed.items()):
        _refuse("continuation report identity drifted")
    for key in (
        "canonical", "point_in_time_data", "direct_ib1c_ingest_authorized",
        "source_authenticity_verified", "official_sec_profile_verified",
        "timezone_interpretation_verified", "prior_code_sha_artifact_verified",
        "halted_on_sec_access",
    ):
        if report[key] is not False:
            _refuse(f"continuation report {key} is not false")
    if report["acquisition_available"] is not True:
        _refuse("continuation report is not an available 16-row pilot")
    counts = {
        "research_looks": 0, "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0, "cumulative_attempt_count": 48,
        "cumulative_distinct_artifact_count": 48, "new_attempt_count": 16,
    }
    if any(type(report[key]) is not int or report[key] != value
           for key, value in counts.items()):
        _refuse("continuation report count or look authority drifted")
    rows = report["rows"]
    if type(rows) is not list or len(rows) != 16:
        _refuse("continuation report does not have exactly 16 rows")
    return rows


@dataclass(frozen=True)
class SecOfflinePilotProjectionReceipt:
    """In-memory compatibility result; never canonical or PIT evidence."""

    report_sha256: str
    inventory_sha256: str
    projections: tuple[SecRawParentProjection, ...]
    _report_bytes: bytes = field(repr=False)
    _expected_accessions: tuple[str, ...] = field(repr=False)
    _projection_sha256s: tuple[str, ...] = field(repr=False)
    _public_pilot: bool = field(repr=False)
    _loader_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._loader_token is not _LOADER_TOKEN:
            _refuse("offline pilot receipt must come from the verified loader")
        self._validate_scope()

    def _validate_scope(self) -> None:
        if type(self._report_bytes) is not bytes or hash_bytes(self._report_bytes) != self.report_sha256:
            _refuse("offline pilot receipt lost its report byte binding")
        report = _canonical_object(self._report_bytes, label="offline pilot report")
        rows = _checked_report(report, inventory_sha256=self.inventory_sha256)
        if (type(self.projections) is not tuple or len(self.projections) != 16
                or type(self._expected_accessions) is not tuple
                or tuple(type(item) is SecRawParentProjection and item.target.accession_number
                         for item in self.projections) != self._expected_accessions
                or tuple(item.sha256 for item in self.projections)
                != self._projection_sha256s):
            _refuse("offline pilot receipt has a partial or altered projection set")
        for row, projection in zip(rows, self.projections, strict=True):
            if type(row) is not dict or type(row.get("candidate")) is not dict:
                _refuse("offline pilot receipt row identity is malformed")
            target = row["candidate"]
            target = {key: target.get(key) for key in (
                "period", "accession_number", "form_type", "filing_date", "issuer_cik",
                "quarterly_zip_sha256", "submission_row_id",
            )} | {"primary_xml_filename": row.get("primary_xml_filename")}
            payload = projection.to_payload()
            if payload["target"] != target:
                _refuse("offline pilot receipt projection target differs from report")
            descriptors = row.get("artifacts")
            if type(descriptors) is not dict or set(descriptors) != {"index", "header", "xml"}:
                _refuse("offline pilot receipt parent descriptors are malformed")
            for role in ("index", "header", "xml"):
                descriptor = descriptors[role]
                if (type(descriptor) is not dict
                        or payload["raw_parents"][role]["sha256"] != descriptor.get("sha256")
                        or payload["raw_parents"][role]["size_bytes"] != descriptor.get("size_bytes")):
                    _refuse("offline pilot receipt projection parent differs from report")
        if self._public_pilot and (
            self.report_sha256 != FINAL_REPORT_SHA256
            or self.inventory_sha256 != INVENTORY_SHA256
            or self._expected_accessions != FIXED_ACCESSIONS
        ):
            _refuse("offline pilot receipt lost its approved source pins")

    def to_payload(self) -> dict[str, object]:
        self._validate_scope()
        rows = []
        for projection in self.projections:
            payload = projection.to_payload()
            rows.append({
                "accession_number": projection.target.accession_number,
                "period": projection.target.period,
                "form_type": projection.target.form_type,
                "projection_sha256": projection.sha256,
                "raw_parent_hashes": {
                    role: payload["raw_parents"][role]["sha256"]
                    for role in ("index", "header", "xml")
                },
                "derived_projection_sha256": payload["derived_projection"]["sha256"],
            })
        return {
            "version": OFFLINE_PILOT_ADAPTER_VERSION,
            "source_report_sha256": self.report_sha256,
            "source_inventory_sha256": self.inventory_sha256,
            "rows": rows,
            "authority": {
                "input_scope": (
                    "retained_noncanonical_pilot" if self._public_pilot
                    else "synthetic_test_receipt"
                ),
                "canonical_evidence": False,
                "point_in_time_data": False,
                "source_authenticated": False,
                "timezone_interpretation_verified": False,
                "official_sec_profile_verified": False,
                "direct_ib1c_ingest_authorized": False,
                "prior_code_sha_artifact_verified": False,
                "first_pass_pacing_trace_verified": False,
                "continuation_journal_replayed": False,
                "outcome_access_authorized": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }


def _load_pilot_projections(
    root: str | Path, *, report_sha256: str, inventory_sha256: str,
    expected_accessions: tuple[str, ...],
) -> SecOfflinePilotProjectionReceipt:
    """Private test seam; only the public wrapper fixes the approved hashes."""
    if (type(report_sha256) is not str or _SHA.fullmatch(report_sha256) is None
            or type(inventory_sha256) is not str or _SHA.fullmatch(inventory_sha256) is None
            or type(expected_accessions) is not tuple or len(expected_accessions) != 16
            or len(set(expected_accessions)) != 16):
        _refuse("fixed pilot pins are malformed")
    path = _plain_root(root)
    report_name = f"sec-pilot-report-{report_sha256}.json"
    if _names(path, label="pilot root") != {
        "commit.json", "inventory.json", "attempts.jsonl", "objects", report_name,
    }:
        _refuse("pilot root inventory differs from the exact continuation")
    try:
        _require_regular_directory(path / "objects", label="pilot objects")
    except SecBulkSnapshotError as exc:
        raise SecOfflinePilotAdapterError(str(exc)) from exc
    # The journal is part of the exact publication shape, but its events are
    # deliberately not replayed or asserted as transport provenance here.
    _read(path, "attempts.jsonl", label="pilot journal", max_bytes=128 * 1024)
    commit = _canonical_object(_read(path, "commit.json", label="pilot commit", max_bytes=4096),
                               label="pilot commit")
    if commit != {"kind": "sec-pilot-commit", "report": report_name,
                  "report_sha256": report_sha256}:
        _refuse("pilot commit does not name the pinned report")
    report_bytes = _read(path, report_name, label="pilot report", max_bytes=2 * 1024 * 1024)
    if hash_bytes(report_bytes) != report_sha256:
        _refuse("pilot report SHA-256 differs from the pinned receipt")
    report = _canonical_object(report_bytes, label="pilot report")
    rows = _checked_report(report, inventory_sha256=inventory_sha256)
    inventory = _canonical_object(
        _read(path, "inventory.json", label="pilot inventory", max_bytes=128 * 1024),
        label="pilot inventory",
    )
    if (set(inventory) != {"kind", "version", "index_route_version", "inventory_sha256",
                           "candidates", "continuation"}
            or inventory["kind"] != "sec-pilot-frozen-inventory"
            or inventory["version"] != _PILOT_VERSION
            or inventory["index_route_version"] != _INDEX_ROUTE_VERSION
            or inventory["inventory_sha256"] != inventory_sha256
            or type(inventory["candidates"]) is not list
            or len(inventory["candidates"]) != 16
            or hash_payload(inventory["candidates"]) != inventory_sha256):
        _refuse("pilot inventory identity or 16-row scope drifted")
    candidates = inventory["candidates"]
    if (tuple(item.get("accession_number") if type(item) is dict else None
              for item in candidates) != expected_accessions):
        _refuse("pilot accessions differ from the approved 16 in order")
    projections: list[SecRawParentProjection] = []
    object_names: set[str] = set()
    urls: list[str] = []
    forms: dict[tuple[str, str], int] = {}
    for candidate, row in zip(candidates, rows, strict=True):
        if (type(candidate) is not dict or set(candidate) != _CANDIDATE_KEYS
                or any(type(value) is not str for value in candidate.values())
                or type(row) is not dict or set(row) != _ROW_KEYS
                or row["candidate"] != candidate
                or row["status"] != "acquired_noncanonical"
                or row["reason"] is not None
                or type(row["first_pass_reason"]) is not str
                or type(row["artifacts"]) is not dict
                or set(row["artifacts"]) != {"index", "header", "xml"}):
            _refuse("pilot row is not an exact acquired triple")
        try:
            target = SecAcquisitionTarget(
                period=candidate["period"], accession_number=candidate["accession_number"],
                form_type=candidate["form_type"], filing_date=candidate["filing_date"],
                issuer_cik=candidate["issuer_cik"],
                quarterly_zip_sha256=candidate["quarterly_zip_sha256"],
                submission_row_id=candidate["submission_row_id"],
                primary_xml_filename=row["primary_xml_filename"],
            )
        except SecAcquisitionPreparationError as exc:
            raise SecOfflinePilotAdapterError(str(exc)) from exc
        forms[target.period, target.form_type] = forms.get((target.period, target.form_type), 0) + 1
        urls.append(target.primary_xml_url)
        raw = {}
        for role in ("index", "header", "xml"):
            descriptor = row["artifacts"][role]
            raw[role] = _descriptor(path, descriptor, role=role)
            name = descriptor["sha256"] + ".bin"
            if name in object_names:
                _refuse("pilot aliases a raw object across rows or roles")
            object_names.add(name)
        tag = row["tag_header_validation"]
        if (type(tag) is not dict or tag.get("raw_header_sha256") != hash_bytes(raw["header"])
                or type(tag.get("raw_header_size_bytes")) is not int
                or tag["raw_header_size_bytes"] != len(raw["header"])
                or tag.get("source_url") != target.header_url
                or any(tag.get(flag) is not False for flag in (
                    "canonical", "direct_ib1c_ingest_authorized",
                    "official_sec_profile_verified", "timezone_interpretation_verified",
                ))
                or tag.get("retrieval_timestamp_unavailable") is not True):
            _refuse("pilot tagged-header receipt differs from its raw parent")
        try:
            projection = derive_sec_raw_parent_projection(
                target, raw["index"], raw["header"], raw["xml"],
            )
        except SecRawParentProjectionError as exc:
            raise SecOfflinePilotAdapterError(str(exc)) from exc
        projected = projection.to_payload()
        if any(projected["raw_parents"][role]["sha256"] != row["artifacts"][role]["sha256"]
               for role in ("index", "header", "xml")):
            _refuse("derived parent hashes disagree with the pilot receipt")
        projections.append(projection)
    if forms != {("2022Q4", "4"): 6, ("2022Q4", "4/A"): 2,
                  ("2023Q1", "4"): 6, ("2023Q1", "4/A"): 2}:
        _refuse("pilot quarter or form distribution drifted")
    continuation = {
        "version": _CONTINUATION_VERSION,
        "first_pass_report_sha256": FIRST_PASS_REPORT_SHA256,
        "first_pass_journal_sha256": FIRST_PASS_JOURNAL_SHA256,
        "first_pass_attempts": 32,
        "first_pass_code_commit_operator_attested": FIRST_PASS_CODE_COMMIT,
        "prior_code_sha_artifact_verified": False,
        "continuation_code_commit_verified": CONTINUATION_CODE_COMMIT,
        "requests": urls,
    }
    if inventory["continuation"] != continuation:
        _refuse("pilot continuation inventory differs from the retained XML paths")
    if len(object_names) != 48 or _names(path / "objects", label="pilot objects") != object_names:
        _refuse("pilot object inventory is not exactly 48 raw parents")
    return SecOfflinePilotProjectionReceipt(
        report_sha256=report_sha256, inventory_sha256=inventory_sha256,
        projections=tuple(projections),
        _report_bytes=report_bytes,
        _expected_accessions=expected_accessions,
        _projection_sha256s=tuple(item.sha256 for item in projections),
        _public_pilot=(report_sha256 == FINAL_REPORT_SHA256
                       and inventory_sha256 == INVENTORY_SHA256
                       and expected_accessions == FIXED_ACCESSIONS),
        _loader_token=_LOADER_TOKEN,
    )


def load_fixed_pilot_projections(root: str | Path) -> SecOfflinePilotProjectionReceipt:
    """Load only the pinned existing pilot; no new source, write, or promotion."""
    return _load_pilot_projections(
        root, report_sha256=FINAL_REPORT_SHA256,
        inventory_sha256=INVENTORY_SHA256, expected_accessions=FIXED_ACCESSIONS,
    )
