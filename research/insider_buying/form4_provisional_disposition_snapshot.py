"""Immutable persistence for the provisional Form 4 disposition report.

IB-1H publishes one canonical JSON byte image for an exact-type IB-1G report.
The report-only writer proves structural self-consistency, not historical
factory origin.  Loading is the evidence trust boundary: it never trusts
serialized rows as Python evidence, requires exact IB-1E evidence, invokes the
public IB-1G builder to reparse that evidence, and requires the stored bytes to
equal the rebuilt canonical bytes.

This boundary is offline and non-authoritative.  Persistence does not prove an
official SEC profile, authenticated amendment coverage, point-in-time security
identity, canonical filtering, lot aggregation, outcomes, or trading fitness.

Residual shared P3: ``exclusive_file_lock`` does not expose its open handle,
so this lane cannot compare that handle's inode with the lock pathname after
acquisition.  A hostile actor could replace only the lock pathname while the
original handle remains locked.  The target/root ancestry and immutable-file
checks below still fail closed, but complete closure belongs in the shared
lock helper and is outside this lane-local milestone.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import (
    ImmutableFileConflictError,
    exclusive_file_lock,
    publish_immutable_bytes,
)
from research.insider_buying.contracts import (
    ClassificationOutcome,
    ContractError,
    TransactionDiagnostic,
)
from research.insider_buying.form4_amendment_reconciliation import (
    MAX_FOOTNOTES_PER_FILING,
    MAX_TOTAL_TRANSACTIONS,
)
from research.insider_buying.form4_multi_period_amendment_evidence import (
    ProfileBoundForm4AmendmentEvidence,
)
from research.insider_buying.form4_provisional_disposition_report import (
    Form4ProvisionalDisposition,
    Form4ProvisionalDispositionReport,
    Form4ProvisionalDispositionReportError,
    build_form4_provisional_disposition_report,
)


FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND = (
    "form4-provisional-disposition-snapshot"
)
FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION = 1
MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES = 256 * 1024 * 1024
MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_JSON_DEPTH = 8

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REPORT_ID_RE = re.compile(
    r"^form4-provisional-disposition-report-(?P<hash_prefix>[0-9a-f]{16})$"
)
_SNAPSHOT_FILE_RE = re.compile(
    r"^(?P<report_id>form4-provisional-disposition-report-[0-9a-f]{16})\.json$"
)
_LOCK_SUFFIX = ".lock"

_BUNDLE_KEYS = frozenset(
    {
        "kind",
        "snapshot_contract_version",
        "report_payload_sha256",
        "report",
    }
)
_REPORT_KEYS = frozenset({"identity", "rows"})
_IDENTITY_KEYS = frozenset(
    {
        "contract_version",
        "builder_git_commit",
        "upstream_evidence_id",
        "upstream_evidence_identity_hash",
        "upstream_parsed_corpus_hash",
        "upstream_source_inventory_hash",
        "row_inventory_hash",
        "transaction_count",
        "candidate_count",
        "quarantine_count",
        "official_profile_compatibility_verified",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "point_in_time_security_identity_verified",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "outcomes_authorized",
        "authorized_outcome_looks",
        "report_id",
    }
)
_ROW_KEYS = frozenset(
    {
        "accession_number",
        "source_sha256",
        "row_index",
        "event_id",
        "derivative",
        "security_title_raw",
        "transaction_date",
        "transaction_code",
        "acquired_disposed_code",
        "shares",
        "price_per_share",
        "purchase_value_usd",
        "direct_indirect",
        "footnote_ids",
        "outcomes",
        "diagnostics",
        "transaction_payload_hash",
        "disposition",
        "row_id",
    }
)
_AUTHORITY_FIELDS = (
    "official_profile_compatibility_verified",
    "official_amendment_link_verified",
    "complete_amendment_coverage_verified",
    "point_in_time_security_identity_verified",
    "canonical_filter_authorized",
    "lot_aggregation_authorized",
    "outcomes_authorized",
)
_OUTCOME_VALUES = frozenset(item.value for item in ClassificationOutcome)
_DIAGNOSTIC_VALUES = frozenset(item.value for item in TransactionDiagnostic)
_DISPOSITION_VALUES = frozenset(item.value for item in Form4ProvisionalDisposition)


class Form4ProvisionalDispositionSnapshotError(ContractError):
    """The bounded IB-1H snapshot contract failed closed."""


def _canonical_json_bytes(payload: object) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _report_payload_bytes(payload: dict[str, object]) -> bytes:
    return canonical_json(payload).encode("utf-8")


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _require_bounded_json_nesting(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_JSON_DEPTH:
                raise Form4ProvisionalDispositionSnapshotError(
                    "REFUSED: disposition snapshot JSON nesting exceeds its limit"
                )
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise Form4ProvisionalDispositionSnapshotError(
                    "REFUSED: disposition snapshot JSON nesting is invalid"
                )
    if depth != 0 or in_string or escaped:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot JSON structure is incomplete"
        )


def _exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot count is invalid"
        )
    return value


def _require_canonical_decimal_text(value: object) -> None:
    if value is None:
        return
    if type(value) is not str or not value:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row decimal is invalid"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row decimal is invalid"
        ) from exc
    if not parsed.is_finite() or str(parsed) != value:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row decimal is not canonical"
        )


def _validate_row_payload(payload: object) -> tuple[str, str, int, str]:
    if type(payload) is not dict or set(payload) != _ROW_KEYS:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row fields are not exact"
        )
    accession = payload.get("accession_number")
    source_hash = payload.get("source_sha256")
    row_index = payload.get("row_index")
    event_id = payload.get("event_id")
    transaction_hash = payload.get("transaction_payload_hash")
    row_id = payload.get("row_id")
    if (
        type(accession) is not str
        or re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession) is None
        or type(source_hash) is not str
        or _SHA256_RE.fullmatch(source_hash) is None
        or type(row_index) is not int
        or row_index < 0
        or type(event_id) is not str
        or _SHA256_RE.fullmatch(event_id) is None
        or type(transaction_hash) is not str
        or _SHA256_RE.fullmatch(transaction_hash) is None
        or type(row_id) is not str
        or _SHA256_RE.fullmatch(row_id) is None
        or type(payload.get("derivative")) is not bool
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row identity is invalid"
        )
    security_title = payload.get("security_title_raw")
    transaction_date = payload.get("transaction_date")
    if security_title is not None and (
        type(security_title) is not str or not security_title
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row text is invalid"
        )
    if transaction_date is not None:
        if type(transaction_date) is not str:
            raise Form4ProvisionalDispositionSnapshotError(
                "REFUSED: disposition snapshot transaction date is invalid"
            )
        try:
            parsed_date = date.fromisoformat(transaction_date)
        except ValueError as exc:
            raise Form4ProvisionalDispositionSnapshotError(
                "REFUSED: disposition snapshot transaction date is invalid"
            ) from exc
        if parsed_date.isoformat() != transaction_date:
            raise Form4ProvisionalDispositionSnapshotError(
                "REFUSED: disposition snapshot transaction date is not canonical"
            )
    for field_name in (
        "transaction_code",
        "acquired_disposed_code",
        "direct_indirect",
    ):
        field_value = payload.get(field_name)
        if field_value is not None and (
            type(field_value) is not str or not field_value
        ):
            raise Form4ProvisionalDispositionSnapshotError(
                "REFUSED: disposition snapshot row value is invalid"
            )
    for field_name in ("shares", "price_per_share", "purchase_value_usd"):
        _require_canonical_decimal_text(payload.get(field_name))

    footnote_ids = payload.get("footnote_ids")
    outcomes = payload.get("outcomes")
    diagnostics = payload.get("diagnostics")
    disposition = payload.get("disposition")
    if (
        type(footnote_ids) is not list
        or len(footnote_ids) > MAX_FOOTNOTES_PER_FILING
        or any(type(item) is not str or not item for item in footnote_ids)
        or footnote_ids != sorted(set(footnote_ids))
        or type(outcomes) is not list
        or not outcomes
        or len(outcomes) > len(_OUTCOME_VALUES)
        or any(type(item) is not str or item not in _OUTCOME_VALUES for item in outcomes)
        or len(set(outcomes)) != len(outcomes)
        or type(diagnostics) is not list
        or len(diagnostics) > len(_DIAGNOSTIC_VALUES)
        or any(
            type(item) is not str or item not in _DIAGNOSTIC_VALUES
            for item in diagnostics
        )
        or len(set(diagnostics)) != len(diagnostics)
        or type(disposition) is not str
        or disposition not in _DISPOSITION_VALUES
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row classification is invalid"
        )
    eligible_value = ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION.value
    eligible = outcomes == [eligible_value]
    expected_disposition = (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE.value
        if eligible
        else Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE.value
    )
    if (eligible_value in outcomes and not eligible) or disposition != expected_disposition:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row routing is inconsistent"
        )
    lineage_payload = dict(payload)
    lineage_payload.pop("row_id")
    if hash_payload(lineage_payload) != row_id:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row ID is invalid"
        )
    return accession, source_hash, row_index, event_id


def _validate_report_payload(payload: object) -> tuple[str, str]:
    if type(payload) is not dict or set(payload) != _REPORT_KEYS:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot report fields are not exact"
        )
    identity = payload.get("identity")
    rows = payload.get("rows")
    if type(identity) is not dict or set(identity) != _IDENTITY_KEYS:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot identity fields are not exact"
        )
    if type(rows) is not list or len(rows) > MAX_TOTAL_TRANSACTIONS:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row inventory exceeds its limit"
        )

    report_id = identity.get("report_id")
    builder_git_commit = identity.get("builder_git_commit")
    match = _REPORT_ID_RE.fullmatch(report_id) if type(report_id) is str else None
    if (
        match is None
        or type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
        or any(identity.get(field_name) is not False for field_name in _AUTHORITY_FIELDS)
        or type(identity.get("authorized_outcome_looks")) is not int
        or identity.get("authorized_outcome_looks") != 0
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot identity is invalid or claims authority"
        )
    for field_name in (
        "upstream_evidence_identity_hash",
        "upstream_parsed_corpus_hash",
        "upstream_source_inventory_hash",
        "row_inventory_hash",
    ):
        field_value = identity.get(field_name)
        if type(field_value) is not str or _SHA256_RE.fullmatch(field_value) is None:
            raise Form4ProvisionalDispositionSnapshotError(
                "REFUSED: disposition snapshot identity hash is invalid"
            )
    if (
        type(identity.get("contract_version")) is not str
        or not identity.get("contract_version")
        or type(identity.get("upstream_evidence_id")) is not str
        or not identity.get("upstream_evidence_id")
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot lineage is invalid"
        )

    transaction_count = _exact_int(
        identity.get("transaction_count"),
        minimum=0,
        maximum=MAX_TOTAL_TRANSACTIONS,
    )
    candidate_count = _exact_int(
        identity.get("candidate_count"),
        minimum=0,
        maximum=transaction_count,
    )
    quarantine_count = _exact_int(
        identity.get("quarantine_count"),
        minimum=0,
        maximum=transaction_count,
    )
    if (
        transaction_count != len(rows)
        or candidate_count + quarantine_count != transaction_count
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot counts are inconsistent"
        )

    row_keys = tuple(_validate_row_payload(row) for row in rows)
    source_row_keys = tuple((item[0], item[2]) for item in row_keys)
    row_ids = tuple(row["row_id"] for row in rows)
    transaction_hashes = tuple(row["transaction_payload_hash"] for row in rows)
    counted_candidates = sum(
        row["disposition"]
        == Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE.value
        for row in rows
    )
    if (
        row_keys != tuple(sorted(row_keys))
        or len(set(row_keys)) != len(row_keys)
        or len(set(source_row_keys)) != len(source_row_keys)
        or len(set(row_ids)) != len(row_ids)
        or len(set(transaction_hashes)) != len(transaction_hashes)
        or counted_candidates != candidate_count
        or hash_payload(rows) != identity.get("row_inventory_hash")
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot row inventory is inconsistent"
        )
    identity_lineage = dict(identity)
    identity_lineage.pop("report_id")
    if match.group("hash_prefix") != hash_payload(identity_lineage)[:16]:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot report ID is invalid"
        )
    return report_id, builder_git_commit


def _snapshot_bytes(report: Form4ProvisionalDispositionReport) -> bytes:
    if type(report) is not Form4ProvisionalDispositionReport:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot requires an exact-type report"
        )
    try:
        report_payload = report.to_payload()
        report_id, _builder_git_commit = _validate_report_payload(report_payload)
        if (
            report.identity.report_id != report_id
            or report.official_profile_compatibility_verified is not False
            or report.official_amendment_link_verified is not False
            or report.complete_amendment_coverage_verified is not False
            or report.point_in_time_security_identity_verified is not False
            or report.canonical_filter_authorized is not False
            or report.lot_aggregation_authorized is not False
            or report.outcomes_authorized is not False
            or report.authorized_outcome_looks != 0
        ):
            raise Form4ProvisionalDispositionSnapshotError(
                "REFUSED: disposition report claims authority"
            )
        report_bytes = _report_payload_bytes(report_payload)
        raw = _canonical_json_bytes(
            {
                "kind": FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND,
                "snapshot_contract_version": (
                    FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION
                ),
                "report_payload_sha256": hash_bytes(report_bytes),
                "report": report_payload,
            }
        )
    except Form4ProvisionalDispositionSnapshotError:
        raise
    except (AttributeError, Form4ProvisionalDispositionReportError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition report cannot be serialized"
        ) from exc
    if len(raw) > MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot exceeds its byte-size limit"
        )
    return raw


def _parse_snapshot_bytes(
    raw: bytes,
    *,
    expected_report_id: str,
) -> tuple[dict[str, object], str]:
    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot exceeds its byte-size limit"
        )
    try:
        text = raw.decode("utf-8", errors="strict")
        _require_bounded_json_nesting(text)
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except Form4ProvisionalDispositionSnapshotError:
        raise
    except (RecursionError, UnicodeDecodeError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot is not valid JSON"
        ) from exc
    if type(value) is not dict or set(value) != _BUNDLE_KEYS:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot fields are not exact"
        )
    declared_report_hash = value.get("report_payload_sha256")
    if (
        value.get("kind") != FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND
        or type(value.get("snapshot_contract_version")) is not int
        or value.get("snapshot_contract_version")
        != FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION
        or type(declared_report_hash) is not str
        or _SHA256_RE.fullmatch(declared_report_hash) is None
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot contract is invalid"
        )
    report_payload = value.get("report")
    try:
        report_id, builder_git_commit = _validate_report_payload(report_payload)
    except Form4ProvisionalDispositionSnapshotError:
        raise
    except (TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot report encoding is invalid"
        ) from exc
    if report_id != expected_report_id:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot filename disagrees with its report"
        )
    if not isinstance(report_payload, dict):  # Exact type checked above.
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot report is invalid"
        )
    if hash_bytes(_report_payload_bytes(report_payload)) != declared_report_hash:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot report hash is invalid"
        )
    try:
        canonical = _canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot is not canonical JSON"
        ) from exc
    if raw != canonical:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot is not canonical JSON"
        )
    return report_payload, builder_git_commit


def _status_is_redirect(value: os.stat_result) -> bool:
    file_attributes = getattr(value, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(value.st_mode) or bool(file_attributes & reparse_attribute)


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    if (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino):
        return True
    return os.name == "nt" and (
        getattr(first, "st_file_attributes", None)
        == getattr(second, "st_file_attributes", None)
        and first.st_size == second.st_size
        and first.st_ctime_ns == second.st_ctime_ns
    )


def _same_file_version(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        _same_file_identity(first, second)
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


def _require_regular_directory(
    path: Path,
    *,
    label: str,
    missing_ok: bool = False,
) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} is missing"
        )
    except OSError as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} is unreadable"
        ) from exc
    if _status_is_redirect(value) or not stat.S_ISDIR(value.st_mode):
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} must be a regular directory"
        )
    return True


def _require_no_redirect_ancestors(path: Path, *, label: str) -> None:
    """Reject every existing redirect component without resolving through it."""

    try:
        absolute = Path(os.path.abspath(os.fspath(path)))
    except (OSError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} path is invalid"
        ) from exc
    if len(str(absolute)) > 32_768:
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} path is invalid"
        )

    parts = absolute.parts
    if not parts:
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} path is invalid"
        )
    current = Path(parts[0])
    components = [current]
    for part in parts[1:]:
        current = current / part
        components.append(current)

    for index, component in enumerate(components):
        try:
            value = component.lstat()
        except FileNotFoundError:
            # A descendant cannot already exist below the first missing
            # lexical component.  The caller rechecks the full ancestry after
            # any directory creation.
            break
        except OSError as exc:
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} ancestry is unreadable"
            ) from exc
        if _status_is_redirect(value):
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} ancestry contains a filesystem redirect"
            )
        if index < len(components) - 1 and not stat.S_ISDIR(value.st_mode):
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} ancestry contains a non-directory component"
            )


def _read_regular_bytes(
    path: Path,
    *,
    label: str,
    require_single_link: bool,
) -> bytes:
    try:
        before = path.lstat()
        if (
            _status_is_redirect(before)
            or not stat.S_ISREG(before.st_mode)
            or (require_single_link and before.st_nlink != 1)
        ):
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} must be a single-link regular immutable file"
            )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                _status_is_redirect(opened)
                or not stat.S_ISREG(opened.st_mode)
                or not _same_file_identity(before, opened)
                or (require_single_link and opened.st_nlink != 1)
            ):
                raise Form4ProvisionalDispositionSnapshotError(
                    f"REFUSED: {label} changed while it was opened"
                )
            if opened.st_size > MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES:
                raise Form4ProvisionalDispositionSnapshotError(
                    f"REFUSED: {label} exceeds its byte-size limit"
                )
            raw = handle.read(
                MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES + 1
            )
            after_read = os.fstat(handle.fileno())
        after_path = path.lstat()
        if (
            not _same_file_version(opened, after_read)
            or not _same_file_version(after_read, after_path)
            or (
                require_single_link
                and (after_read.st_nlink != 1 or after_path.st_nlink != 1)
            )
        ):
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} changed while it was read"
            )
        if len(raw) != after_read.st_size:
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} was not read as one complete byte image"
            )
        if len(raw) > MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES:
            raise Form4ProvisionalDispositionSnapshotError(
                f"REFUSED: {label} exceeds its byte-size limit"
            )
        return raw
    except Form4ProvisionalDispositionSnapshotError:
        raise
    except OSError as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            f"REFUSED: {label} is missing or unreadable"
        ) from exc


def _prepare_output_root(output_root: str | Path) -> Path:
    if not isinstance(output_root, (str, Path)) or not str(output_root):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot output root is invalid"
        )
    if len(str(output_root)) > 32_768:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot output root is invalid"
        )
    try:
        root = Path(output_root)
        _require_no_redirect_ancestors(
            root, label="disposition snapshot output root"
        )
        if not _require_regular_directory(
            root,
            label="disposition snapshot output root",
            missing_ok=True,
        ):
            root.mkdir(parents=True, exist_ok=True)
        _require_no_redirect_ancestors(
            root, label="disposition snapshot output root"
        )
        _require_regular_directory(
            root, label="disposition snapshot output root"
        )
        canonical_root = root.resolve(strict=True)
        _require_no_redirect_ancestors(
            canonical_root, label="disposition snapshot output root"
        )
        _require_regular_directory(
            canonical_root, label="disposition snapshot output root"
        )
        return canonical_root
    except Form4ProvisionalDispositionSnapshotError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot output root is unavailable"
        ) from exc


def _require_regular_lock_slot(lock_path: Path) -> None:
    try:
        value = lock_path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot publication lock is unreadable"
        ) from exc
    if (
        _status_is_redirect(value)
        or not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot publication lock must be a "
            "single-link regular file"
        )


def write_form4_provisional_disposition_snapshot(
    report: Form4ProvisionalDispositionReport,
    output_root: str | Path,
) -> Path:
    """Atomically publish one immutable canonical IB-1H report snapshot."""

    raw = _snapshot_bytes(report)
    report_id = report.identity.report_id
    root = _prepare_output_root(output_root)
    target = root / f"{report_id}.json"
    lock_path = root / f".{report_id}{_LOCK_SUFFIX}"
    _require_regular_lock_slot(lock_path)
    try:
        lock_manager = exclusive_file_lock(lock_path)
        with lock_manager:
            _require_no_redirect_ancestors(
                root, label="disposition snapshot output root"
            )
            _require_regular_directory(
                root, label="disposition snapshot output root"
            )
            _require_regular_lock_slot(lock_path)
            try:
                target_status = target.lstat()
            except FileNotFoundError:
                target_status = None
            except OSError as exc:
                raise Form4ProvisionalDispositionSnapshotError(
                    "REFUSED: disposition snapshot target is unreadable"
                ) from exc
            if target_status is not None:
                actual = _read_regular_bytes(
                    target,
                    label="committed disposition snapshot",
                    require_single_link=True,
                )
                if actual != raw:
                    raise Form4ProvisionalDispositionSnapshotError(
                        "REFUSED: immutable disposition snapshot conflicts with "
                        "attempted publication"
                    )
                _parse_snapshot_bytes(actual, expected_report_id=report_id)
                return target
            try:
                publish_immutable_bytes(target, raw)
            except ImmutableFileConflictError as exc:
                actual = _read_regular_bytes(
                    target,
                    label="committed disposition snapshot",
                    require_single_link=True,
                )
                if actual != raw:
                    raise Form4ProvisionalDispositionSnapshotError(
                        "REFUSED: immutable disposition snapshot conflicts with "
                        "attempted publication"
                    ) from exc
            actual = _read_regular_bytes(
                target,
                label="committed disposition snapshot",
                require_single_link=True,
            )
            if actual != raw:
                raise Form4ProvisionalDispositionSnapshotError(
                    "REFUSED: committed disposition snapshot changed after publication"
                )
            _parse_snapshot_bytes(actual, expected_report_id=report_id)
            return target
    except Form4ProvisionalDispositionSnapshotError:
        raise
    except OSError as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot publication failed"
        ) from exc


def load_form4_provisional_disposition_snapshot(
    snapshot_path: str | Path,
    *,
    evidence: ProfileBoundForm4AmendmentEvidence,
) -> Form4ProvisionalDispositionReport:
    """Rebuild exact upstream evidence before accepting persisted report bytes."""

    if type(evidence) is not ProfileBoundForm4AmendmentEvidence:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot requires exact profile-bound evidence"
        )
    if not isinstance(snapshot_path, (str, Path)) or not str(snapshot_path):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot path is invalid"
        )
    path = Path(snapshot_path)
    filename_match = _SNAPSHOT_FILE_RE.fullmatch(path.name)
    if filename_match is None:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot filename is invalid"
        )
    _require_no_redirect_ancestors(
        path.parent, label="disposition snapshot parent directory"
    )
    _require_regular_directory(
        path.parent, label="disposition snapshot parent directory"
    )
    raw = _read_regular_bytes(
        path,
        label="disposition snapshot",
        require_single_link=True,
    )
    _report_payload, builder_git_commit = _parse_snapshot_bytes(
        raw,
        expected_report_id=filename_match.group("report_id"),
    )
    try:
        rebuilt = build_form4_provisional_disposition_report(
            evidence,
            builder_git_commit=builder_git_commit,
        )
        expected = _snapshot_bytes(rebuilt)
    except (Form4ProvisionalDispositionReportError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot upstream evidence cannot be rebuilt"
        ) from exc
    if (
        rebuilt.identity.report_id != filename_match.group("report_id")
        or raw != expected
    ):
        raise Form4ProvisionalDispositionSnapshotError(
            "REFUSED: disposition snapshot disagrees with rebuilt upstream evidence"
        )
    return rebuilt


__all__ = [
    "FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_KIND",
    "FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_VERSION",
    "Form4ProvisionalDispositionSnapshotError",
    "MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_BYTES",
    "MAX_FORM4_PROVISIONAL_DISPOSITION_SNAPSHOT_JSON_DEPTH",
    "load_form4_provisional_disposition_snapshot",
    "write_form4_provisional_disposition_snapshot",
]
