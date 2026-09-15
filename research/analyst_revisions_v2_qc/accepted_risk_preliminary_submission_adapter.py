"""Signed, one-use host adapter for the accepted-risk preliminary QC run.

The adapter is intentionally narrower than the formal evaluator adapter.  It
binds one already-authenticated compact package and its exact five-file QC
projection, spends an owner-only local permit before any network access,
creates one new private project, uploads the package activation object last,
compiles, and creates exactly one backtest.  Status polling is statistics-free.

After a completed run, a separately signed ``formal_qc_result_read`` authority
spends a second one-use local permit before exactly one ``backtests/read``
call.  Only the 34 preliminary ``ARV2_*`` aggregate custom statistics are
selected, validated, returned, and persisted.  Raw provider rows, price rows,
logs, charts, orders, trades, deployment, and trading are outside this module.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
import threading
import time
import weakref
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping, NoReturn

from research.analyst_revisions_v2 import preregistration

from . import accepted_risk_preliminary_package as package_builder
from . import accepted_risk_preliminary_qc_projection as projection_builder
from . import accepted_risk_preliminary_qc_runtime as preliminary_runtime
from . import accepted_risk_preliminary_rating_evaluator as preliminary_evaluator
from . import formal_submission_adapter as formal
from .formal_qc_transport import FormalQcTransport
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_formal_execution_owner_signature,
    require_formal_result_read_owner_signature,
)


class AcceptedRiskPreliminarySubmissionError(ValueError):
    """A local authority, plan, QC envelope, or aggregate result is invalid."""


class AcceptedRiskPreliminarySubmissionLocked(RuntimeError):
    """A durable one-use permit was spent and the external action is final."""

    def __init__(self, phase: str, permit_id: str, detail: str) -> None:
        super().__init__(
            f"{phase}: {detail}; accepted-risk preliminary permit remains consumed"
        )
        self.phase = phase
        self.permit_id = permit_id


class AcceptedRiskPreliminaryTerminalFailure(RuntimeError):
    """The exact preliminary run reached a non-success terminal state."""

    def __init__(self, receipt: "AcceptedRiskPreliminaryTerminalStatus") -> None:
        super().__init__(
            "accepted-risk preliminary backtest reached authenticated terminal failure"
        )
        self.receipt = receipt


PLAN_SCHEMA = "arv2-accepted-risk-preliminary-qc-submission-plan-v1"
EXECUTION_AUTHORITY_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-execution-authority-v1"
)
EXECUTION_PERMIT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-execution-one-use-permit-v1"
)
PRECREATE_CONTROL_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-pre-create-control-v1"
)
LAUNCH_RECOVERY_PERMIT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-launch-recovery-one-use-permit-v1"
)
LAUNCH_SCHEMA = "arv2-accepted-risk-preliminary-qc-launch-receipt-v1"
TERMINAL_SCHEMA = "arv2-accepted-risk-preliminary-qc-terminal-status-v1"
RESULT_AUTHORITY_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-result-read-authority-v1"
)
RESULT_PERMIT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-result-read-one-use-permit-v1"
)
RESULT_RECEIPT_SCHEMA = (
    "arv2-accepted-risk-preliminary-qc-aggregate-result-receipt-v1"
)
UPLOAD_ENTRY_SCHEMA = "arv2-accepted-risk-preliminary-qc-submission-upload-v1"
HOST_CLOSURE_SCHEMA = "arv2-accepted-risk-preliminary-qc-host-closure-v1"
MAX_CONTROL_BYTES = 1024 * 1024
MAX_HOST_SOURCE_BYTES = 4 * 1024 * 1024
MAX_PROJECT_NAME_BYTES = 100
MAX_BACKTEST_NAME_BYTES = 200
MAX_COMPILE_POLLS = 120
MAX_STATUS_POLLS = 1_440
COMPILE_POLL_SECONDS = 2
STATUS_POLL_SECONDS = 30
QC_DEFAULT_RESEARCH_NOTEBOOK_PATH = "research.ipynb"
RECOVERED_LAUNCH_INITIAL_STATUS = "RECOVERED_BY_STATISTICS_FREE_LIST"

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_CELL_NAME = re.compile(
    r"ARV2_IC_(CUR|CEN)_(FIRM|GLOBAL)_H(1|5|20|60)_"
    r"(2020_2025|2021_2025)\Z"
)
# Bind the complete lane-local host implementation, not merely the handful of
# entry-point modules.  Package authentication and aggregate validation call
# through several lane helpers (including canonical/artifact IO and the cloud
# runtime/evaluator contract); a signature must not survive a fresh-process
# change to any of those semantics.  The two directories are inventoried
# exactly and deterministically, while the small set of imported helpers that
# live outside them is named explicitly.
HOST_CODE_DIRECTORY_PATHS = (
    "research/analyst_revisions_v2",
    "research/analyst_revisions_v2_qc",
)
HOST_CODE_PATHS = (
    "data/__init__.py",
    "data/exchange_calendar.py",
    "data/financial_primitives.py",
    "research/__init__.py",
    "research/quantconnect.py",
    "scripts/build_arv2_historical_preopen_bridge.py",
    "scripts/build_arv2_massive_input_pair.py",
    "scripts/build_arv2_preopen_input.py",
    "scripts/capture_arv2_massive.py",
    "scripts/capture_arv2_sharadar.py",
)
_PINNED_REQUIRE_PACKAGE = package_builder.require_accepted_risk_preliminary_package
_PINNED_ITER_UPLOADS = package_builder.iter_accepted_risk_preliminary_upload_objects
_PINNED_REQUIRE_PROJECTION = (
    projection_builder.require_accepted_risk_preliminary_qc_projection
)
_PINNED_EXPECTED_RESULT_NAMES = tuple(
    preliminary_runtime.EXPECTED_CUSTOM_SUMMARY_STATISTIC_NAMES
)
_PINNED_REQUIRE_EXECUTION_SIGNATURE = require_formal_execution_owner_signature
_PINNED_REQUIRE_RESULT_SIGNATURE = require_formal_result_read_owner_signature
_PINNED_LOAD_INFRASTRUCTURE_LEDGER = preregistration.load_infrastructure_look_ledger
_PINNED_REQUIRE_INFRASTRUCTURE_LEDGER = (
    preregistration.require_infrastructure_look_ledger
)
_PINNED_INFRASTRUCTURE_LEDGER = _PINNED_REQUIRE_INFRASTRUCTURE_LEDGER(
    _PINNED_LOAD_INFRASTRUCTURE_LEDGER()
)
_PINNED_REQUIRE_TRANSPORT = formal._require_concrete_transport
_PINNED_TRANSPORT_CALL = formal._transport_call
_PINNED_READ_PROJECTS = formal._read_project_inventory
_PINNED_PROJECT_RECORD = formal._project_record
_PINNED_CREATED_PROJECT = formal._created_project
_PINNED_READ_FILES = formal._read_files
_PINNED_SUCCESS = formal._success
_PINNED_OBJECT_METADATA = formal._object_metadata_matches
_PINNED_COMPILE_ID = formal._compile_id
_PINNED_COMPILE_STATE = formal._compile_state
_PINNED_CREATED_BACKTEST = formal._created_backtest
_PINNED_PARSE_STATUS = formal.parse_statistics_free_backtest_list
_PINNED_PARSE_UNIQUE_RUN = formal._parse_statistics_free_unique_project_run
_PINNED_BACKTEST_STATUS_KEYS = formal._BACKTEST_STATUS_KEYS
_PINNED_DISCARDED_BACKTEST_KEYS = formal._DISCARDED_BACKTEST_SUMMARY_KEYS
_PINNED_COMPILE_TERMINAL_STATES = formal.COMPILE_TERMINAL_STATES
_PINNED_BACKTEST_TERMINAL_STATES = formal.BACKTEST_TERMINAL_STATUSES
_PINNED_LEXISTS = os.path.lexists
_PINNED_SCANDIR = os.scandir

EXECUTION_ACTIONS = (
    "authenticate",
    "projects/read_exact_name_inventory",
    "projects/create_private_exact_name_once",
    "object/set_package_objects_activation_last",
    "object/properties_verify_exact_key_size_md5",
    "files/read_exact_inventory",
    "files/delete_only_exact_default_research_ipynb",
    "files/create_or_update_exact_five_file_projection",
    "files/readback_exact_five_source_bytes",
    "compile/create_once",
    "compile/read_state_only_with_bounded_wait",
    "persist_authenticated_pre_create_control",
    "backtests/create_once",
    "recover_unique_named_run_statistics_free_once_if_create_is_ambiguous",
    "backtests/list_identity_status_includeStatistics_false",
)
RESULT_ACTIONS = (
    "backtests/read_once",
    "select_exact_expected_ARV2_custom_summary_keys_only",
    "persist_exact_validated_aggregate_custom_statistics_only",
)


def _look_accounting(*, stage: str = "reservation") -> dict[str, object]:
    """Return prospective, launched, or authenticated-result look accounting."""
    if stage not in {"reservation", "launch", "result"}:
        _error("preliminary look-accounting stage changed")
    launched = stage in {"launch", "result"}
    aggregate_authenticated = stage == "result"
    binding = _PINNED_REQUIRE_INFRASTRUCTURE_LEDGER(
        _PINNED_INFRASTRUCTURE_LEDGER
    )
    return {
        "schema": "arv2-qc-research-look-accounting-v1",
        "classification": "development_evaluation",
        "evaluation_id": "arv2-eval-stock-historical-qc-001",
        "shared_look_ledger_entry_id": "R-055",
        "accounting_stage": stage,
        "run_level_looks_before": 55,
        "run_level_looks_after": 56 if launched else 55,
        "planned_run_level_looks_after_launch": 56,
        "arv2_development_evaluations_before": 2,
        "arv2_development_evaluations_after": 3 if launched else 2,
        "planned_arv2_development_evaluations_after_launch": 3,
        "planned_maximum_preliminary_ic_cell_count": 32,
        "emitted_preliminary_ic_cell_count": (
            32 if aggregate_authenticated else 0
        ),
        "lifetime_alpha_cell_floor_before": 484,
        "lifetime_alpha_cell_floor_after": (
            516 if aggregate_authenticated else 484
        ),
        "aggregate_result_authenticated": aggregate_authenticated,
        "infrastructure_looks_before": 23,
        "infrastructure_looks_after": 23,
        "authenticated_infrastructure_look_count": 23,
        "infrastructure_look_ledger_id": binding.ledger_id,
        "infrastructure_look_ledger_hash": binding.ledger_hash,
        "infrastructure_look_ledger_artifact_sha256": binding.artifact_sha256,
        "permanent_looks_before": 0,
        "permanent_looks_after": 0,
        "confirmatory_looks_before": 0,
        "confirmatory_looks_after": 0,
        "confirmatory_look_spent": False,
        "execution_permit_alone_consumes_look": False,
        "pre_create_control_marks_launch_ambiguity_and_consumes_look": True,
        "backtest_create_attempt_consumes_look_on_success_failure_or_ambiguity": True,
        "technical_corrected_rerun_requires_new_ledger_entry": True,
        "retry_may_overwrite_shared_ledger_entry": False,
    }


def _error(message: str) -> NoReturn:
    raise AcceptedRiskPreliminarySubmissionError(message)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary submission value is not canonical ASCII JSON"
        ) from exc


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > MAX_CONTROL_BYTES:
        _error(f"{name} is not bounded exact bytes")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=unique,
            parse_constant=lambda _item: (_ for _ in ()).throw(
                ValueError("nonstandard constant")
            ),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"{name} is not strict ASCII JSON"
        ) from exc
    if type(value) is not dict or _canonical(value) != payload:
        _error(f"{name} is not one canonical JSON object")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _error(f"{name} is not an exact SHA-256")
    return value


def _safe_name(value: object, name: str, maximum: int) -> str:
    if (
        type(value) is not str
        or _SAFE_NAME.fullmatch(value) is None
        or len(value.encode("utf-8")) > maximum
    ):
        _error(f"{name} is not an exact safe bounded name")
    return value


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        _error(f"{name} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"{name} is not canonical UTC"
        ) from exc
    if (
        parsed.tzinfo != timezone.utc
        or parsed.microsecond != 0
        or parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value
    ):
        _error(f"{name} is not canonical UTC")
    return value


def _private_directory(value: Path) -> Path:
    if type(value) is not type(Path()) or not value.is_absolute() or ".." in value.parts:
        _error("preliminary control directory must be an absolute exact Path")
    current = Path(value.anchor)
    try:
        for part in value.parts[1:]:
            current /= part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                _error("preliminary control directory ancestry must be nonsymlink")
        observed = os.stat(value)
    except AcceptedRiskPreliminarySubmissionError:
        raise
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary control directory is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o700
        or observed.st_uid != os.getuid()
        or value.resolve(strict=True) != value
    ):
        _error("preliminary control directory must be owner-only mode 0700")
    return value


def _read_private(path: Path, name: str) -> bytes:
    if type(path) is not type(Path()) or path.parent != _private_directory(path.parent):
        _error(f"{name} path changed")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(f"{name} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        payload = os.read(descriptor, MAX_CONTROL_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        "st_dev", "st_ino", "st_uid", "st_mode", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if (
        any(getattr(before, field) != getattr(after, field) for field in identity)
        or not stat.S_ISREG(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or before.st_size != len(payload)
        or not 0 < len(payload) <= MAX_CONTROL_BYTES
    ):
        _error(f"{name} is not one stable owner-only regular file")
    return payload


def _write_private_once(path: Path, payload: bytes, name: str) -> None:
    directory = _private_directory(path.parent)
    if (
        type(path.name) is not str
        or not path.name
        or "/" in path.name
        or type(payload) is not bytes
        or not 0 < len(payload) <= MAX_CONTROL_BYTES
    ):
        _error(f"{name} path or payload changed")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(path, flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short control write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"{name} already exists or could not be published"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    directory_descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    if _read_private(path, name) != payload:
        _error(f"{name} changed after publication")


def _identified(schema: str, prefix: str, record: dict[str, object]) -> tuple[str, str, bytes]:
    seed = {"schema": schema, "id": None, "sha256": None, **record}
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    identity = prefix + digest[:24]
    return identity, digest, _canonical({**seed, "id": identity, "sha256": digest})


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryHostSourceBinding:
    path: str
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryHostClosureBinding:
    closure_id: str
    closure_sha256: str
    worktree_root: str
    sources: tuple[AcceptedRiskPreliminaryHostSourceBinding, ...]
    canonical_document: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": HOST_CLOSURE_SCHEMA,
            "closure_id": self.closure_id,
            "closure_sha256": self.closure_sha256,
            "worktree_root": self.worktree_root,
            "sources": [item.to_record() for item in self.sources],
        }


def _read_host_source(path: Path, *, root: Path) -> bytes:
    try:
        path.relative_to(root)
        original = os.lstat(path)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary host source escaped the exact worktree"
        ) from exc
    if resolved != path or stat.S_ISLNK(original.st_mode):
        _error("preliminary host source path uses a symlink")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary host source is unavailable"
        ) from exc
    try:
        before = os.fstat(descriptor)
        chunks = []
        remaining = MAX_HOST_SOURCE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 256 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        "st_dev", "st_ino", "st_uid", "st_mode", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if (
        any(getattr(original, field) != getattr(before, field) for field in identity)
        or
        any(getattr(before, field) != getattr(after, field) for field in identity)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or before.st_mode & 0o022
        or before.st_size != len(payload)
        or len(payload) > MAX_HOST_SOURCE_BYTES
        or (payload and not payload.endswith(b"\n"))
        or b"\r" in payload
    ):
        _error("preliminary host source is not one stable canonical file")
    return payload


def _walk_host_python_sources(directory: Path, root: Path) -> tuple[str, ...]:
    paths = []
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            with _PINNED_SCANDIR(current) as scanner:
                entries = sorted(scanner, key=lambda item: item.name)
        except OSError as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary host source directory is unavailable"
            ) from exc
        for entry in entries:
            try:
                if entry.is_symlink():
                    _error("preliminary host source inventory contains a symlink")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                    continue
                regular = entry.is_file(follow_symlinks=False)
            except OSError as exc:
                raise AcceptedRiskPreliminarySubmissionError(
                    "preliminary host source inventory changed during scan"
                ) from exc
            if not regular:
                _error("preliminary host source inventory contains a special node")
            if entry.name.endswith(".py"):
                paths.append(str(Path(entry.path).relative_to(root)))
    return tuple(paths)


def _host_code_inventory_paths(root: Path) -> tuple[str, ...]:
    paths = list(HOST_CODE_PATHS)
    for relative_directory in HOST_CODE_DIRECTORY_PATHS:
        directory = root / relative_directory
        try:
            original = os.lstat(directory)
            resolved = directory.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary host code directory escaped the exact worktree"
            ) from exc
        if (
            resolved != directory
            or stat.S_ISLNK(original.st_mode)
            or not stat.S_ISDIR(original.st_mode)
        ):
            _error("preliminary host code directory changed or uses a symlink")
        paths.extend(_walk_host_python_sources(directory, root))
    result = tuple(sorted(paths))
    if (
        not result
        or len(result) != len(set(result))
        or any(type(item) is not str or not item.endswith(".py") for item in result)
    ):
        _error("preliminary host source inventory changed")
    return result


def _build_host_closure(worktree_root: Path) -> AcceptedRiskPreliminaryHostClosureBinding:
    if type(worktree_root) is not type(Path()) or not worktree_root.is_absolute():
        _error("preliminary worktree root must be an absolute exact Path")
    try:
        root = worktree_root.resolve(strict=True)
    except OSError as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "preliminary worktree root is unavailable"
        ) from exc
    if root != worktree_root or not root.is_dir():
        _error("preliminary worktree root changed")
    sources = tuple(
        AcceptedRiskPreliminaryHostSourceBinding(
            relative,
            hashlib.sha256(
                payload := _read_host_source(root / relative, root=root)
            ).hexdigest(),
            len(payload),
        )
        for relative in _host_code_inventory_paths(root)
    )
    seed = {
        "schema": HOST_CLOSURE_SCHEMA,
        "closure_id": None,
        "closure_sha256": None,
        "worktree_root": str(root),
        "sources": [item.to_record() for item in sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    identity = "arv2-preliminary-qc-host-closure-" + digest[:24]
    document = _canonical(
        {**seed, "closure_id": identity, "closure_sha256": digest}
    )
    return AcceptedRiskPreliminaryHostClosureBinding(
        identity, digest, str(root), sources, document
    )


def _require_host_closure(
    value: AcceptedRiskPreliminaryHostClosureBinding,
) -> AcceptedRiskPreliminaryHostClosureBinding:
    if type(value) is not AcceptedRiskPreliminaryHostClosureBinding:
        _error("preliminary host closure type changed")
    rebuilt = _build_host_closure(Path(value.worktree_root))
    if value != rebuilt or value.canonical_document != rebuilt.canonical_document:
        _error("preliminary live host source closure changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryUploadEntry:
    schema: str
    role: str
    ordinal: int
    object_store_key: str
    byte_count: int
    content_sha256: str
    content_md5: str
    activation_manifest: bool

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminarySubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    organization_id_sha256: str
    project_name: str
    backtest_name: str
    control_directory: Path
    package_id: str
    package_sha256: str
    evaluator_manifest_id: str
    evaluator_manifest_sha256: str
    activation_manifest_key: str
    activation_manifest_sha256: str
    upload_entries: tuple[AcceptedRiskPreliminaryUploadEntry, ...]
    projection_id: str
    projection_sha256: str
    project_source_set_sha256: str
    source_files: tuple[projection_builder.PreliminaryQcSourceFile, ...]
    host_closure: AcceptedRiskPreliminaryHostClosureBinding
    expected_custom_statistic_names: tuple[str, ...]
    expected_custom_statistic_names_sha256: str
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    package: package_builder.AcceptedRiskPreliminaryPackage = dataclasses.field(repr=False)
    projection: projection_builder.AcceptedRiskPreliminaryQcProjection = dataclasses.field(repr=False)


def _upload_entries(package) -> tuple[AcceptedRiskPreliminaryUploadEntry, ...]:
    descriptors = package.upload_objects
    entries = []
    for index, ((descriptor, payload), expected) in enumerate(
        zip(_PINNED_ITER_UPLOADS(package), descriptors, strict=True)
    ):
        if (
            descriptor is not expected
            or descriptor.ordinal != expected.ordinal
            or len(payload) != descriptor.byte_count
            or hashlib.sha256(payload).hexdigest() != descriptor.content_sha256
            or descriptor.activation_manifest != (index == len(descriptors) - 1)
        ):
            _error("preliminary package upload sequence changed")
        entries.append(
            AcceptedRiskPreliminaryUploadEntry(
                UPLOAD_ENTRY_SCHEMA,
                descriptor.role,
                descriptor.ordinal,
                descriptor.object_store_key,
                descriptor.byte_count,
                descriptor.content_sha256,
                hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                descriptor.activation_manifest,
            )
        )
    if not entries or entries[-1].activation_manifest is not True:
        _error("preliminary package activation is not last")
    return tuple(entries)


def _plan_record(
    *, package, projection, organization_hash: str, project_name: str,
    backtest_name: str, control_directory: Path,
    upload_entries: tuple[AcceptedRiskPreliminaryUploadEntry, ...],
    host_closure: AcceptedRiskPreliminaryHostClosureBinding,
) -> dict[str, object]:
    source_records = [item.to_record() for item in projection.source_files]
    source_hash = hashlib.sha256(_canonical(source_records)).hexdigest()
    names_hash = hashlib.sha256(
        _canonical(list(_PINNED_EXPECTED_RESULT_NAMES))
    ).hexdigest()
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": None,
        "plan_sha256": None,
        "organization_id_sha256": organization_hash,
        "project_name": project_name,
        "backtest_name": backtest_name,
        "control_directory": str(control_directory),
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "evaluator_manifest_id": package.evaluator_manifest_id,
        "evaluator_manifest_sha256": package.evaluator_manifest_sha256,
        "activation_manifest_key": projection.activation_manifest_key,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "upload_entries": [item.to_record() for item in upload_entries],
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "project_source_set_sha256": source_hash,
        "source_files": source_records,
        "host_code_closure": host_closure.to_record(),
        "expected_custom_statistic_names": list(_PINNED_EXPECTED_RESULT_NAMES),
        "expected_custom_statistic_names_sha256": names_hash,
        "look_accounting": _look_accounting(),
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "include_statistics_during_status": False,
        "result_read_calls": 1,
        "preliminary": True,
        "formal": False,
        "deployment": False,
        "orders": False,
        "trading": False,
        "retry_inside_adapter": False,
    }


def build_accepted_risk_preliminary_submission_plan(
    *,
    package: package_builder.AcceptedRiskPreliminaryPackage,
    projection: projection_builder.AcceptedRiskPreliminaryQcProjection,
    organization_id: str,
    project_name: str,
    backtest_name: str,
    control_directory: Path,
    worktree_root: Path,
) -> AcceptedRiskPreliminarySubmissionPlan:
    package = _PINNED_REQUIRE_PACKAGE(package)
    projection = _PINNED_REQUIRE_PROJECTION(projection)
    _safe_name(organization_id, "organization id", 512)
    _safe_name(project_name, "project name", MAX_PROJECT_NAME_BYTES)
    _safe_name(backtest_name, "backtest name", MAX_BACKTEST_NAME_BYTES)
    control_directory = _private_directory(control_directory)
    if (
        projection.package_id != package.package_id
        or projection.package_sha256 != package.package_sha256
        or len(projection.source_files) != 5
        or tuple(item.project_path for item in projection.source_files)
        != tuple(sorted(projection_builder.PROJECT_SOURCE_PATHS + ("main.py",)))
    ):
        _error("preliminary package and five-file projection are not exact peers")
    uploads = _upload_entries(package)
    host_closure = _build_host_closure(worktree_root)
    organization_hash = hashlib.sha256(organization_id.encode("utf-8")).hexdigest()
    record = _plan_record(
        package=package,
        projection=projection,
        organization_hash=organization_hash,
        project_name=project_name,
        backtest_name=backtest_name,
        control_directory=control_directory,
        upload_entries=uploads,
        host_closure=host_closure,
    )
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    identity = "arv2-preliminary-qc-submission-" + digest[:24]
    source_hash = record["project_source_set_sha256"]
    names_hash = record["expected_custom_statistic_names_sha256"]
    value = AcceptedRiskPreliminarySubmissionPlan(
        identity,
        digest,
        organization_id,
        organization_hash,
        project_name,
        backtest_name,
        control_directory,
        package.package_id,
        package.package_sha256,
        package.evaluator_manifest_id,
        package.evaluator_manifest_sha256,
        projection.activation_manifest_key,
        projection.activation_manifest_sha256,
        uploads,
        projection.projection_id,
        projection.projection_sha256,
        source_hash,
        projection.source_files,
        host_closure,
        _PINNED_EXPECTED_RESULT_NAMES,
        names_hash,
        MAX_COMPILE_POLLS,
        MAX_STATUS_POLLS,
        1,
        package,
        projection,
    )
    _PINNED_REQUIRE_PACKAGE(package)
    _PINNED_REQUIRE_PROJECTION(projection)
    return value


def require_accepted_risk_preliminary_submission_plan(
    value: AcceptedRiskPreliminarySubmissionPlan,
) -> AcceptedRiskPreliminarySubmissionPlan:
    if type(value) is not AcceptedRiskPreliminarySubmissionPlan:
        _error("preliminary submission plan type changed")
    rebuilt = build_accepted_risk_preliminary_submission_plan(
        package=value.package,
        projection=value.projection,
        organization_id=value.organization_id,
        project_name=value.project_name,
        backtest_name=value.backtest_name,
        control_directory=value.control_directory,
        worktree_root=Path(value.host_closure.worktree_root),
    )
    if value != rebuilt:
        _error("preliminary submission plan changed")
    return value


def _submission_plan_path(plan: AcceptedRiskPreliminarySubmissionPlan) -> Path:
    return plan.control_directory / (
        "submission-plan-" + plan.plan_sha256[:24] + ".json"
    )


def _submission_plan_bytes(plan: AcceptedRiskPreliminarySubmissionPlan) -> bytes:
    record = _plan_record(
        package=plan.package,
        projection=plan.projection,
        organization_hash=plan.organization_id_sha256,
        project_name=plan.project_name,
        backtest_name=plan.backtest_name,
        control_directory=plan.control_directory,
        upload_entries=plan.upload_entries,
        host_closure=_require_host_closure(plan.host_closure),
    )
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    identity = "arv2-preliminary-qc-submission-" + digest[:24]
    if digest != plan.plan_sha256 or identity != plan.plan_id:
        _error("preliminary persisted plan identity changed")
    return _canonical(
        {**record, "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256}
    )


def persist_accepted_risk_preliminary_submission_plan(
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> Path:
    """Publish or reauthenticate the exact canonical plan in its private run dir."""
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    path = _submission_plan_path(plan)
    payload = _submission_plan_bytes(plan)
    try:
        observed = _read_private(path, "submission plan")
    except AcceptedRiskPreliminarySubmissionError:
        _write_private_once(path, payload, "submission plan")
    else:
        if observed != payload:
            _error("persisted preliminary submission plan changed")
    return path


def load_accepted_risk_preliminary_submission_plan(
    *,
    plan_path: Path,
    package: package_builder.AcceptedRiskPreliminaryPackage,
    projection: projection_builder.AcceptedRiskPreliminaryQcProjection,
    organization_id: str,
) -> AcceptedRiskPreliminarySubmissionPlan:
    """Rebuild a plan in a later process and authenticate it to durable bytes."""
    _safe_name(organization_id, "organization id", 512)
    payload = _read_private(plan_path, "submission plan")
    raw = _strict_object(payload, "submission plan")
    project_name = _safe_name(
        raw.get("project_name"), "persisted project name", MAX_PROJECT_NAME_BYTES
    )
    backtest_name = _safe_name(
        raw.get("backtest_name"), "persisted backtest name", MAX_BACKTEST_NAME_BYTES
    )
    raw_control_directory = raw.get("control_directory")
    if (
        type(raw_control_directory) is not str
        or not raw_control_directory
        or len(raw_control_directory.encode("utf-8")) > 4096
    ):
        _error("persisted control directory changed")
    control_directory = Path(raw_control_directory)
    raw_host_closure = raw.get("host_code_closure")
    if (
        type(raw_host_closure) is not dict
        or type(raw_host_closure.get("worktree_root")) is not str
        or not raw_host_closure["worktree_root"]
        or len(raw_host_closure["worktree_root"].encode("utf-8")) > 4096
    ):
        _error("persisted preliminary host closure changed")
    rebuilt = build_accepted_risk_preliminary_submission_plan(
        package=package,
        projection=projection,
        organization_id=organization_id,
        project_name=project_name,
        backtest_name=backtest_name,
        control_directory=control_directory,
        worktree_root=Path(raw_host_closure["worktree_root"]),
    )
    if (
        plan_path != _submission_plan_path(rebuilt)
        or payload != _submission_plan_bytes(rebuilt)
    ):
        _error("persisted preliminary submission plan does not match inputs")
    return rebuilt


def _execution_authority(plan: AcceptedRiskPreliminarySubmissionPlan) -> bytes:
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    return _canonical(
        {
            "schema": EXECUTION_AUTHORITY_SCHEMA,
            "signature_purpose": "formal_qc_execution",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "organization_id_sha256": plan.organization_id_sha256,
            "project_name": plan.project_name,
            "backtest_name": plan.backtest_name,
            "package_id": plan.package_id,
            "package_sha256": plan.package_sha256,
            "activation_manifest_sha256": plan.activation_manifest_sha256,
            "projection_id": plan.projection_id,
            "projection_sha256": plan.projection_sha256,
            "project_source_set_sha256": plan.project_source_set_sha256,
            "package_upload_count": len(plan.upload_entries),
            "project_source_count": len(plan.source_files),
            "host_code_closure": _require_host_closure(
                plan.host_closure
            ).to_record(),
            "look_accounting": _look_accounting(),
            "actions": list(EXECUTION_ACTIONS),
            "maximum_backtest_submissions": 1,
            "statistics_free_status": True,
            "result_read_authority_separate": True,
            "retries_inside_adapter": 0,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
    )


def render_accepted_risk_preliminary_execution_authority_candidate(
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> bytes:
    return _execution_authority(plan)


def _require_execution_signature(
    value: OwnerSignatureAuthority | None, payload: bytes,
) -> OwnerSignatureAuthority:
    try:
        return _PINNED_REQUIRE_EXECUTION_SIGNATURE(value, authority_payload=payload)
    except (OwnerSignatureAuthorityError, TypeError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "detached formal_qc_execution owner signature is unavailable"
        ) from exc


def _require_result_signature(
    value: OwnerSignatureAuthority | None, payload: bytes,
) -> OwnerSignatureAuthority:
    try:
        return _PINNED_REQUIRE_RESULT_SIGNATURE(value, authority_payload=payload)
    except (OwnerSignatureAuthorityError, TypeError) as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            "detached formal_qc_result_read owner signature is unavailable"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminarySubmissionPermit:
    permit_id: str
    permit_sha256: str
    plan_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    permit_path: Path
    permit_bytes: bytes = dataclasses.field(repr=False)


def _execution_permit_path(plan) -> Path:
    return plan.control_directory / (
        "execution-permit-" + plan.plan_sha256[:24] + ".json"
    )


def _build_execution_permit(plan, signature, started_at_utc):
    _utc(started_at_utc, "execution started_at")
    record = {
        "plan_sha256": plan.plan_sha256,
        "owner_signature_sha256": _sha(
            signature.authority_sha256, "execution signature authority"
        ),
        "look_accounting": _look_accounting(),
        "started_at_utc": started_at_utc,
        "submission_attempt_count": 1,
        "ambiguous_submission_consumes_permit": True,
        "retry_authorized_inside_adapter": False,
    }
    identity, digest, payload = _identified(
        EXECUTION_PERMIT_SCHEMA, "arv2-preliminary-qc-execution-permit-", record
    )
    return AcceptedRiskPreliminarySubmissionPermit(
        identity,
        digest,
        plan.plan_sha256,
        signature.authority_sha256,
        started_at_utc,
        _execution_permit_path(plan),
        payload,
    )


def _spend_execution_permit(plan, signature, started_at_utc):
    permit = _build_execution_permit(plan, signature, started_at_utc)
    try:
        _write_private_once(permit.permit_path, permit.permit_bytes, "execution permit")
    except AcceptedRiskPreliminarySubmissionError as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "execution_permit", permit.permit_id, "permit already spent or unavailable"
        ) from exc
    return permit


def require_accepted_risk_preliminary_submission_permit(
    value: AcceptedRiskPreliminarySubmissionPermit,
    *, plan: AcceptedRiskPreliminarySubmissionPlan,
    owner_signature: OwnerSignatureAuthority,
) -> AcceptedRiskPreliminarySubmissionPermit:
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_signature(owner_signature, _execution_authority(plan))
    return _require_execution_permit_bytes(value, plan)


def _require_execution_permit_bytes(
    value: AcceptedRiskPreliminarySubmissionPermit,
    plan: AcceptedRiskPreliminarySubmissionPlan,
) -> AcceptedRiskPreliminarySubmissionPermit:
    if type(value) is not AcceptedRiskPreliminarySubmissionPermit:
        _error("preliminary execution permit type changed")
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_path != _execution_permit_path(plan)
        or _read_private(value.permit_path, "execution permit")
        != value.permit_bytes
    ):
        _error("preliminary execution permit changed")
    raw = _strict_object(value.permit_bytes, "execution permit")
    seed = dict(raw)
    if set(seed) != {
        "schema", "id", "sha256", "plan_sha256",
        "owner_signature_sha256", "look_accounting", "started_at_utc",
        "submission_attempt_count", "ambiguous_submission_consumes_permit",
        "retry_authorized_inside_adapter",
    }:
        _error("preliminary execution permit fields changed")
    declared_id = seed.pop("id")
    declared_sha = seed.pop("sha256")
    seed["id"] = None
    seed["sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        raw.get("schema") != EXECUTION_PERMIT_SCHEMA
        or raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("owner_signature_sha256") != value.owner_signature_sha256
        or raw.get("look_accounting") != _look_accounting()
        or raw.get("started_at_utc") != value.started_at_utc
        or raw.get("submission_attempt_count") != 1
        or raw.get("ambiguous_submission_consumes_permit") is not True
        or raw.get("retry_authorized_inside_adapter") is not False
        or declared_id != value.permit_id
        or declared_sha != value.permit_sha256
        or digest != value.permit_sha256
        or value.permit_id != "arv2-preliminary-qc-execution-permit-" + digest[:24]
    ):
        _error("preliminary execution permit identity changed")
    _sha(value.owner_signature_sha256, "execution permit owner signature")
    _utc(value.started_at_utc, "execution permit started_at")
    return value


def load_accepted_risk_preliminary_submission_permit(
    *, plan: AcceptedRiskPreliminarySubmissionPlan,
) -> AcceptedRiskPreliminarySubmissionPermit:
    """Authenticate and rehydrate the already-spent execution permit."""
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    path = _execution_permit_path(plan)
    payload = _read_private(path, "execution permit")
    raw = _strict_object(payload, "execution permit")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256",
        "owner_signature_sha256", "look_accounting", "started_at_utc",
        "submission_attempt_count", "ambiguous_submission_consumes_permit",
        "retry_authorized_inside_adapter",
    }:
        _error("preliminary execution permit fields changed")
    value = AcceptedRiskPreliminarySubmissionPermit(
        raw["id"],
        raw["sha256"],
        raw["plan_sha256"],
        raw["owner_signature_sha256"],
        raw["started_at_utc"],
        path,
        payload,
    )
    return _require_execution_permit_bytes(value, plan)


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryPreCreateControl:
    control_id: str
    control_sha256: str
    plan_sha256: str
    permit_sha256: str
    project_id: int
    compile_id: str
    backtest_name: str
    control_path: Path
    control_bytes: bytes = dataclasses.field(repr=False)


def _precreate_control_path(plan) -> Path:
    return plan.control_directory / (
        "pre-create-control-" + plan.plan_sha256[:24] + ".json"
    )


def _build_precreate_control(plan, permit, project_id, compile_id):
    record = {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "package_sha256": plan.package_sha256,
        "projection_sha256": plan.projection_sha256,
        "project_id": project_id,
        "compile_id": compile_id,
        "backtest_name": plan.backtest_name,
        "look_accounting": _look_accounting(stage="launch"),
        "backtests_create_call_limit": 1,
        "backtests_create_may_have_occurred": True,
        "statistics_free_recovery_only": True,
    }
    identity, digest, payload = _identified(
        PRECREATE_CONTROL_SCHEMA,
        "arv2-preliminary-qc-pre-create-",
        record,
    )
    return AcceptedRiskPreliminaryPreCreateControl(
        identity, digest, plan.plan_sha256, permit.permit_sha256,
        project_id, compile_id, plan.backtest_name,
        _precreate_control_path(plan), payload,
    )


def _require_precreate_control(value, plan, permit):
    if type(value) is not AcceptedRiskPreliminaryPreCreateControl:
        _error("preliminary pre-create control type changed")
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.backtest_name != plan.backtest_name
        or value.control_path != _precreate_control_path(plan)
        or _read_private(value.control_path, "pre-create control")
        != value.control_bytes
    ):
        _error("preliminary pre-create control lineage changed")
    raw = _strict_object(value.control_bytes, "pre-create control")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "permit_sha256",
        "package_sha256", "projection_sha256", "project_id", "compile_id",
        "backtest_name", "look_accounting", "backtests_create_call_limit",
        "backtests_create_may_have_occurred", "statistics_free_recovery_only",
    }:
        _error("preliminary pre-create control fields changed")
    seed = dict(raw)
    declared_id = seed.pop("id")
    declared_sha = seed.pop("sha256")
    seed["id"] = None
    seed["sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        raw.get("schema") != PRECREATE_CONTROL_SCHEMA
        or raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("permit_sha256") != permit.permit_sha256
        or raw.get("package_sha256") != plan.package_sha256
        or raw.get("projection_sha256") != plan.projection_sha256
        or type(value.project_id) is not int
        or value.project_id <= 0
        or raw.get("project_id") != value.project_id
        or raw.get("compile_id") != value.compile_id
        or raw.get("backtest_name") != value.backtest_name
        or raw.get("look_accounting") != _look_accounting(stage="launch")
        or raw.get("backtests_create_call_limit") != 1
        or raw.get("backtests_create_may_have_occurred") is not True
        or raw.get("statistics_free_recovery_only") is not True
        or declared_id != value.control_id
        or declared_sha != value.control_sha256
        or digest != value.control_sha256
        or value.control_id != "arv2-preliminary-qc-pre-create-" + digest[:24]
    ):
        _error("preliminary pre-create control identity changed")
    _safe_name(value.compile_id, "pre-create compile id", 512)
    return value


def load_accepted_risk_preliminary_pre_create_control(
    *, plan: AcceptedRiskPreliminarySubmissionPlan,
    permit: AcceptedRiskPreliminarySubmissionPermit,
) -> AcceptedRiskPreliminaryPreCreateControl:
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(permit, plan)
    path = _precreate_control_path(plan)
    payload = _read_private(path, "pre-create control")
    raw = _strict_object(payload, "pre-create control")
    value = AcceptedRiskPreliminaryPreCreateControl(
        raw.get("id"), raw.get("sha256"), raw.get("plan_sha256"),
        raw.get("permit_sha256"), raw.get("project_id"), raw.get("compile_id"),
        raw.get("backtest_name"), path, payload,
    )
    return _require_precreate_control(value, plan, permit)


def _launch_recovery_permit_path(plan) -> Path:
    return plan.control_directory / (
        "launch-recovery-permit-" + plan.plan_sha256[:24] + ".json"
    )


def _launch_recovery_permit_record(plan, permit, control):
    return {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "precreate_control_sha256": control.control_sha256,
        "look_accounting": _look_accounting(stage="launch"),
        "statistics_free_backtests_list_call_limit": 1,
        "retry_inside_adapter": False,
    }


def _spend_launch_recovery_permit(plan, permit, control) -> str:
    identity, digest, payload = _identified(
        LAUNCH_RECOVERY_PERMIT_SCHEMA,
        "arv2-preliminary-qc-launch-recovery-permit-",
        _launch_recovery_permit_record(plan, permit, control),
    )
    if identity != "arv2-preliminary-qc-launch-recovery-permit-" + digest[:24]:
        _error("preliminary launch-recovery permit identity changed")
    try:
        _write_private_once(
            _launch_recovery_permit_path(plan),
            payload,
            "launch-recovery permit",
        )
    except AcceptedRiskPreliminarySubmissionError as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "launch_recovery", permit.permit_id, "recovery permit already spent"
        ) from exc
    return digest


def _require_launch_recovery_permit(plan, permit, control, expected_sha256):
    _sha(expected_sha256, "launch-recovery permit")
    payload = _read_private(
        _launch_recovery_permit_path(plan), "launch-recovery permit"
    )
    identity, digest, expected = _identified(
        LAUNCH_RECOVERY_PERMIT_SCHEMA,
        "arv2-preliminary-qc-launch-recovery-permit-",
        _launch_recovery_permit_record(plan, permit, control),
    )
    if (
        payload != expected
        or digest != expected_sha256
        or identity
        != "arv2-preliminary-qc-launch-recovery-permit-" + digest[:24]
    ):
        _error("preliminary launch-recovery permit lineage changed")
    return digest


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    permit_sha256: str
    precreate_control_sha256: str
    launch_recovery_permit_sha256: str | None
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryTerminalStatus:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    permit_sha256: str
    launch_sha256: str
    project_id: int
    backtest_id: str
    terminal_status: str
    poll_count: int
    include_statistics: bool
    result_values_selected: bool


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskPreliminaryResultReadPermit:
    permit_id: str
    permit_sha256: str
    plan_sha256: str
    launch_sha256: str
    terminal_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    permit_path: Path
    permit_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskPreliminaryAggregateResult:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    launch_sha256: str
    terminal_sha256: str
    result_permit_sha256: str
    project_id: int
    backtest_id: str
    custom_statistics: tuple[tuple[str, str], ...]
    custom_statistics_sha256: str
    persisted_path: Path
    backtests_read_call_count: int
    raw_provider_rows_selected: bool
    logs_selected: bool
    charts_selected: bool
    orders_selected: bool


def _launch_record(value: AcceptedRiskPreliminaryLaunchReceipt) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "permit_sha256": value.permit_sha256,
        "precreate_control_sha256": value.precreate_control_sha256,
        "launch_recovery_permit_sha256": value.launch_recovery_permit_sha256,
        "look_accounting": _look_accounting(stage="launch"),
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
    }


def _terminal_record(value: AcceptedRiskPreliminaryTerminalStatus) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "permit_sha256": value.permit_sha256,
        "launch_sha256": value.launch_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "terminal_status": value.terminal_status,
        "poll_count": value.poll_count,
        "include_statistics": value.include_statistics,
        "result_values_selected": value.result_values_selected,
    }


def _result_record(value: AcceptedRiskPreliminaryAggregateResult) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "launch_sha256": value.launch_sha256,
        "terminal_sha256": value.terminal_sha256,
        "result_permit_sha256": value.result_permit_sha256,
        "look_accounting": _look_accounting(stage="result"),
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "custom_statistics": [list(item) for item in value.custom_statistics],
        "custom_statistics_sha256": value.custom_statistics_sha256,
        "persisted_path": str(value.persisted_path),
        "backtests_read_call_count": value.backtests_read_call_count,
        "raw_provider_rows_selected": value.raw_provider_rows_selected,
        "logs_selected": value.logs_selected,
        "charts_selected": value.charts_selected,
        "orders_selected": value.orders_selected,
    }


def _launch_receipt_path(plan: AcceptedRiskPreliminarySubmissionPlan) -> Path:
    return plan.control_directory / (
        "launch-receipt-" + plan.plan_sha256[:24] + ".json"
    )


def _terminal_receipt_path(plan: AcceptedRiskPreliminarySubmissionPlan) -> Path:
    return plan.control_directory / (
        "terminal-receipt-" + plan.plan_sha256[:24] + ".json"
    )


def _identified_receipt_bytes(
    *, schema: str, prefix: str, record: dict[str, object],
    receipt_id: str, receipt_sha256: str,
) -> bytes:
    expected_id, expected_sha, payload = _identified(schema, prefix, record)
    if receipt_id != expected_id or receipt_sha256 != expected_sha:
        _error("preliminary durable receipt identity changed")
    return payload


def _launch_receipt_bytes(value: AcceptedRiskPreliminaryLaunchReceipt) -> bytes:
    return _identified_receipt_bytes(
        schema=LAUNCH_SCHEMA,
        prefix="arv2-preliminary-qc-launch-",
        record=_launch_record(value),
        receipt_id=value.receipt_id,
        receipt_sha256=value.receipt_sha256,
    )


def _terminal_receipt_bytes(value: AcceptedRiskPreliminaryTerminalStatus) -> bytes:
    return _identified_receipt_bytes(
        schema=TERMINAL_SCHEMA,
        prefix="arv2-preliminary-qc-terminal-",
        record=_terminal_record(value),
        receipt_id=value.receipt_id,
        receipt_sha256=value.receipt_sha256,
    )


def _load_launch_receipt_impl(*, plan, permit, register_launch):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(permit, plan)
    control = load_accepted_risk_preliminary_pre_create_control(
        plan=plan, permit=permit
    )
    payload = _read_private(_launch_receipt_path(plan), "launch receipt")
    raw = _strict_object(payload, "launch receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "permit_sha256",
        "precreate_control_sha256", "launch_recovery_permit_sha256",
        "look_accounting", "project_id", "compile_id", "backtest_id", "backtest_name",
        "initial_status",
    }:
        _error("preliminary launch receipt fields changed")
    value = AcceptedRiskPreliminaryLaunchReceipt(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["permit_sha256"],
        raw["precreate_control_sha256"], raw["launch_recovery_permit_sha256"],
        raw["project_id"], raw["compile_id"], raw["backtest_id"],
        raw["backtest_name"], raw["initial_status"],
    )
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.precreate_control_sha256 != control.control_sha256
        or value.project_id != control.project_id
        or value.compile_id != control.compile_id
        or raw.get("look_accounting") != _look_accounting(stage="launch")
        or type(value.project_id) is not int
        or value.project_id <= 0
        or value.backtest_name != plan.backtest_name
    ):
        _error("preliminary launch receipt lineage changed")
    if value.initial_status == RECOVERED_LAUNCH_INITIAL_STATUS:
        _require_launch_recovery_permit(
            plan,
            permit,
            control,
            value.launch_recovery_permit_sha256,
        )
    elif value.launch_recovery_permit_sha256 is not None:
        _error("preliminary direct launch unexpectedly binds recovery")
    _safe_name(value.compile_id, "persisted compile id", 512)
    _safe_name(value.backtest_id, "persisted backtest id", 512)
    _safe_name(value.initial_status, "persisted initial status", 512)
    if payload != _launch_receipt_bytes(value):
        _error("persisted preliminary launch receipt changed")
    register_launch(value, plan, permit)
    return value


def _load_terminal_receipt_impl(
    *, plan, permit, launch, require_launch, register_terminal,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(permit, plan)
    require_launch(launch, plan, permit)
    payload = _read_private(_terminal_receipt_path(plan), "terminal receipt")
    raw = _strict_object(payload, "terminal receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "permit_sha256",
        "launch_sha256", "project_id", "backtest_id", "terminal_status",
        "poll_count", "include_statistics", "result_values_selected",
    }:
        _error("preliminary terminal receipt fields changed")
    value = AcceptedRiskPreliminaryTerminalStatus(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["permit_sha256"],
        raw["launch_sha256"], raw["project_id"], raw["backtest_id"],
        raw["terminal_status"], raw["poll_count"], raw["include_statistics"],
        raw["result_values_selected"],
    )
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or type(value.terminal_status) is not str
        or value.terminal_status not in _PINNED_BACKTEST_TERMINAL_STATES
        or type(value.poll_count) is not int
        or not 1 <= value.poll_count <= plan.status_poll_limit
        or value.include_statistics is not False
        or value.result_values_selected is not False
        or payload != _terminal_receipt_bytes(value)
    ):
        _error("preliminary terminal receipt lineage changed")
    register_terminal(value, plan, permit, launch)
    return value


def _make_return_authority():
    lock = threading.RLock()
    launch_state: dict[int, tuple[object, ...]] = {}
    terminal_state: dict[int, tuple[object, ...]] = {}
    result_state: dict[int, tuple[object, ...]] = {}
    authority_pid = os.getpid()

    def register_launch(value, plan, permit):
        with lock:
            launch_state[id(value)] = (
                weakref.ref(value), plan, permit, _canonical(_launch_record(value)),
                authority_pid,
            )

    def require_launch(value, plan, permit):
        if type(value) is not AcceptedRiskPreliminaryLaunchReceipt:
            _error("preliminary launch receipt type changed")
        with lock:
            state = launch_state.get(id(value))
        if (
            state is None
            or state[0]() is not value
            or state[1] is not plan
            or state[2] is not permit
            or state[3] != _canonical(_launch_record(value))
            or state[4] != os.getpid()
        ):
            _error("preliminary launch receipt lacks process-return authority")
        seed = {"schema": LAUNCH_SCHEMA, "id": None, "sha256": None, **_launch_record(value)}
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        if value.receipt_sha256 != digest or value.receipt_id != "arv2-preliminary-qc-launch-" + digest[:24]:
            _error("preliminary launch receipt identity changed")
        return value

    def register_terminal(value, plan, permit, launch):
        require_launch(launch, plan, permit)
        with lock:
            terminal_state[id(value)] = (
                weakref.ref(value), plan, permit, launch,
                _canonical(_terminal_record(value)), authority_pid,
            )

    def require_terminal(value, plan, permit, launch):
        require_launch(launch, plan, permit)
        if type(value) is not AcceptedRiskPreliminaryTerminalStatus:
            _error("preliminary terminal receipt type changed")
        with lock:
            state = terminal_state.get(id(value))
        if (
            state is None
            or state[0]() is not value
            or state[1] is not plan
            or state[2] is not permit
            or state[3] is not launch
            or state[4] != _canonical(_terminal_record(value))
            or state[5] != os.getpid()
        ):
            _error("preliminary terminal receipt lacks process-return authority")
        seed = {"schema": TERMINAL_SCHEMA, "id": None, "sha256": None, **_terminal_record(value)}
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        if value.receipt_sha256 != digest or value.receipt_id != "arv2-preliminary-qc-terminal-" + digest[:24]:
            _error("preliminary terminal receipt identity changed")
        return value

    def register_result(value, plan, permit, launch, terminal, result_permit):
        require_terminal(terminal, plan, permit, launch)
        with lock:
            result_state[id(value)] = (
                weakref.ref(value), plan, permit, launch, terminal, result_permit,
                _canonical(_result_record(value)), authority_pid,
            )

    def require_result(value, plan, permit, launch, terminal, result_permit):
        require_terminal(terminal, plan, permit, launch)
        if type(value) is not AcceptedRiskPreliminaryAggregateResult:
            _error("preliminary result receipt type changed")
        with lock:
            state = result_state.get(id(value))
        if (
            state is None
            or state[0]() is not value
            or state[1] is not plan
            or state[2] is not permit
            or state[3] is not launch
            or state[4] is not terminal
            or state[5] is not result_permit
            or state[6] != _canonical(_result_record(value))
            or state[7] != os.getpid()
        ):
            _error("preliminary result receipt lacks process-return authority")
        seed = {"schema": RESULT_RECEIPT_SCHEMA, "id": None, "sha256": None, **_result_record(value)}
        digest = hashlib.sha256(_canonical(seed)).hexdigest()
        if value.receipt_sha256 != digest or value.receipt_id != "arv2-preliminary-qc-result-" + digest[:24]:
            _error("preliminary result receipt identity changed")
        return value

    return register_launch, require_launch, register_terminal, require_terminal, register_result, require_result


(
    _register_launch,
    _require_launch,
    _register_terminal,
    _require_terminal,
    _register_result,
    _require_result,
) = _make_return_authority()
del _make_return_authority


def _wait(seconds: int) -> None:
    if seconds not in (COMPILE_POLL_SECONDS, STATUS_POLL_SECONDS):
        _error("preliminary polling interval changed")
    time.sleep(seconds)


def _transport(client, capability, method: str, *args):
    return _PINNED_TRANSPORT_CALL(client, capability, method, *args)


def _new_launch(
    plan, permit, control, backtest_id, initial,
    launch_recovery_permit_sha256=None,
):
    if initial == RECOVERED_LAUNCH_INITIAL_STATUS:
        _sha(launch_recovery_permit_sha256, "launch-recovery permit")
    elif launch_recovery_permit_sha256 is not None:
        _error("preliminary direct launch unexpectedly binds recovery")
    record = {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "precreate_control_sha256": control.control_sha256,
        "launch_recovery_permit_sha256": launch_recovery_permit_sha256,
        "project_id": control.project_id,
        "compile_id": control.compile_id,
        "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "initial_status": initial,
    }
    identity, digest, _payload = _identified(
        LAUNCH_SCHEMA,
        "arv2-preliminary-qc-launch-",
        {**record, "look_accounting": _look_accounting(stage="launch")},
    )
    return AcceptedRiskPreliminaryLaunchReceipt(identity, digest, **record)


def _execute_accepted_risk_preliminary_submission_once_impl(
    *, plan, owner_signature, client, started_at_utc,
    minter, signature_verifier, transport_verifier, register_launch,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    signature = signature_verifier(owner_signature, _execution_authority(plan))
    persist_accepted_risk_preliminary_submission_plan(plan)
    transport_verifier(client)
    permit = _spend_execution_permit(plan, signature, started_at_utc)
    capability = minter(
        transport=client,
        scope="submission",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-submission-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "package_sha256": plan.package_sha256,
            "projection_sha256": plan.projection_sha256,
        },
        call_budget={
            "authenticate": 1,
            "projects/read": 2,
            "projects/create": 1,
            "object/set": len(plan.upload_entries),
            "object/properties": len(plan.upload_entries),
            "files/read": 2,
            "files/create": len(plan.source_files),
            "files/update": len(plan.source_files),
            "files/delete": 1,
            "compile/create": 1,
            "compile/read": plan.compile_poll_limit,
            "backtests/create": 1,
        },
    )
    try:
        _transport(client, capability, "_request_json", "authenticate", {})
        inventory = _PINNED_READ_PROJECTS(
            _transport(client, capability, "_request_json", "projects/read", {})
        )
        if any(type(item) is dict and item.get("name") == plan.project_name for item in inventory):
            _error("exact preliminary project already exists")
        created = _PINNED_CREATED_PROJECT(
            _transport(
                client,
                capability,
                "_request_json",
                "projects/create",
                {"name": plan.project_name, "language": "Py"},
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(created["projectId"])
        exact = _PINNED_READ_PROJECTS(
            _transport(
                client,
                capability,
                "_request_json",
                "projects/read",
                {"projectId": project_id},
            )
        )
        if len(exact) != 1:
            _error("new preliminary project identity is ambiguous")
        _PINNED_PROJECT_RECORD(
            exact[0], name=plan.project_name, organization_id=plan.organization_id
        )

        observed_entries = []
        for descriptor, payload in _PINNED_ITER_UPLOADS(plan.package):
            entry = plan.upload_entries[len(observed_entries)]
            if (
                descriptor.object_store_key != entry.object_store_key
                or descriptor.content_sha256 != entry.content_sha256
                or descriptor.byte_count != entry.byte_count
                or hashlib.md5(payload, usedforsecurity=False).hexdigest()
                != entry.content_md5
                or descriptor.activation_manifest != entry.activation_manifest
            ):
                _error("preliminary package changed during upload")
            _transport(
                client,
                capability,
                "_set_object_multipart",
                plan.organization_id,
                entry.object_store_key,
                payload,
            )
            _PINNED_OBJECT_METADATA(
                _transport(
                    client,
                    capability,
                    "_read_object_properties",
                    plan.organization_id,
                    entry.object_store_key,
                ),
                entry,
            )
            observed_entries.append(entry)
        if tuple(observed_entries) != plan.upload_entries or observed_entries[-1].activation_manifest is not True:
            _error("preliminary package upload inventory changed")

        existing = _PINNED_READ_FILES(
            _transport(
                client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        projected = {item.project_path: item for item in plan.source_files}
        unexpected = set(existing) - set(projected)
        if unexpected - {QC_DEFAULT_RESEARCH_NOTEBOOK_PATH}:
            _error("new preliminary project contains an unprojected source")
        if QC_DEFAULT_RESEARCH_NOTEBOOK_PATH in unexpected:
            _PINNED_SUCCESS(
                _transport(
                    client,
                    capability,
                    "_request_json",
                    "files/delete",
                    {"projectId": project_id, "name": QC_DEFAULT_RESEARCH_NOTEBOOK_PATH},
                ),
                frozenset({"success", "errors", "messages"}),
                "files/delete",
            )
        for path, source in projected.items():
            endpoint = "files/update" if path in existing else "files/create"
            _PINNED_SUCCESS(
                _transport(
                    client,
                    capability,
                    "_request_json",
                    endpoint,
                    {
                        "projectId": project_id,
                        "name": path,
                        "content": source.source_bytes.decode("ascii"),
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                endpoint,
            )
        readback = _PINNED_READ_FILES(
            _transport(
                client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if set(readback) != set(projected):
            _error("preliminary project source inventory is not exact")
        for path, source in projected.items():
            try:
                payload = readback[path].encode("ascii")
            except UnicodeError as exc:
                raise AcceptedRiskPreliminarySubmissionError(
                    "preliminary source readback is not exact ASCII"
                ) from exc
            if (
                payload != source.source_bytes
                or len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest() != source.content_sha256
            ):
                _error("preliminary project source readback changed")
        compile_id = _PINNED_COMPILE_ID(
            _transport(
                client, capability, "_request_json", "compile/create",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = _PINNED_COMPILE_STATE(
                _transport(
                    client, capability, "_request_json", "compile/read",
                    {"projectId": project_id, "compileId": compile_id},
                ),
                compile_id,
            )
            if compile_state in _PINNED_COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                _error("preliminary compile polling exhausted")
            _wait(COMPILE_POLL_SECONDS)
        if compile_state != "BuildSuccess":
            _error("preliminary project did not compile BuildSuccess")
        control = _build_precreate_control(
            plan, permit, project_id, compile_id
        )
        _write_private_once(
            control.control_path,
            control.control_bytes,
            "pre-create control",
        )
        _require_precreate_control(control, plan, permit)
        backtest_id, initial = _PINNED_CREATED_BACKTEST(
            _transport(
                client,
                capability,
                "_request_json",
                "backtests/create",
                {
                    "projectId": project_id,
                    "compileId": compile_id,
                    "backtestName": plan.backtest_name,
                },
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        launch = _new_launch(plan, permit, control, backtest_id, initial)
        _write_private_once(
            _launch_receipt_path(plan),
            _launch_receipt_bytes(launch),
            "launch receipt",
        )
        register_launch(launch, plan, permit)
        return permit, launch
    except AcceptedRiskPreliminarySubmissionLocked:
        raise
    except Exception as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "submission", permit.permit_id, type(exc).__name__
        ) from exc


def _recover_accepted_risk_preliminary_launch_once_impl(
    *, plan, owner_signature, permit, client,
    minter, signature_verifier, transport_verifier,
    load_launch, register_launch,
):
    """Recover the unique run after create may have succeeded without a receipt."""
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    signature_verifier(owner_signature, _execution_authority(plan))
    _require_execution_permit_bytes(permit, plan)
    launch_path = _launch_receipt_path(plan)
    if _PINNED_LEXISTS(launch_path):
        return load_launch(
            plan=plan,
            permit=permit,
            register_launch=register_launch,
        )
    control = load_accepted_risk_preliminary_pre_create_control(
        plan=plan, permit=permit
    )
    transport_verifier(client)
    recovery_permit_sha256 = _spend_launch_recovery_permit(
        plan, permit, control
    )
    capability = minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-launch-recovery-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "precreate_control_sha256": control.control_sha256,
            "project_id": control.project_id,
            "backtest_name": control.backtest_name,
        },
        call_budget={"backtests/list": 1},
    )
    try:
        status = _PINNED_PARSE_UNIQUE_RUN(
            _transport(
                client,
                capability,
                "_request_json",
                "backtests/list",
                {
                    "projectId": control.project_id,
                    "includeStatistics": False,
                },
            ),
            expected_project_id=control.project_id,
            expected_backtest_name=control.backtest_name,
        )
        launch = _new_launch(
            plan,
            permit,
            control,
            status.backtest_id,
            RECOVERED_LAUNCH_INITIAL_STATUS,
            recovery_permit_sha256,
        )
        _write_private_once(
            launch_path,
            _launch_receipt_bytes(launch),
            "launch receipt",
        )
        register_launch(launch, plan, permit)
        return launch
    except AcceptedRiskPreliminarySubmissionLocked:
        raise
    except Exception as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "launch_recovery", permit.permit_id, type(exc).__name__
        ) from exc


def _new_terminal(plan, permit, launch, status, count):
    record = {
        "plan_sha256": plan.plan_sha256,
        "permit_sha256": permit.permit_sha256,
        "launch_sha256": launch.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": status,
        "poll_count": count,
        "include_statistics": False,
        "result_values_selected": False,
    }
    identity, digest, _payload = _identified(
        TERMINAL_SCHEMA, "arv2-preliminary-qc-terminal-", record
    )
    return AcceptedRiskPreliminaryTerminalStatus(identity, digest, **record)


def _inspect_accepted_risk_preliminary_terminal_status_impl(
    *, plan, owner_signature, permit, launch, client,
    minter, signature_verifier, transport_verifier, require_launch,
    register_terminal,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    signature_verifier(owner_signature, _execution_authority(plan))
    _require_execution_permit_bytes(permit, plan)
    require_launch(launch, plan, permit)
    transport_verifier(client)
    capability = minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-status-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_sha256": launch.receipt_sha256,
        },
        call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = _PINNED_PARSE_STATUS(
                _transport(
                    client,
                    capability,
                    "_request_json",
                    "backtests/list",
                    {"projectId": launch.project_id, "includeStatistics": False},
                ),
                expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise AcceptedRiskPreliminarySubmissionLocked(
                "terminal_status", permit.permit_id, type(exc).__name__
            ) from exc
        if status.status in _PINNED_BACKTEST_TERMINAL_STATES:
            terminal = _new_terminal(plan, permit, launch, status.status, index + 1)
            _write_private_once(
                _terminal_receipt_path(plan),
                _terminal_receipt_bytes(terminal),
                "terminal receipt",
            )
            register_terminal(terminal, plan, permit, launch)
            if terminal.terminal_status != "Completed.":
                raise AcceptedRiskPreliminaryTerminalFailure(terminal)
            return terminal
        if index + 1 == plan.status_poll_limit:
            raise AcceptedRiskPreliminarySubmissionLocked(
                "terminal_status", permit.permit_id, "poll limit exhausted"
            )
        _wait(STATUS_POLL_SECONDS)
    raise AssertionError("unreachable preliminary status loop")


def _result_permit_path(plan):
    return plan.control_directory / (
        "result-read-permit-" + plan.plan_sha256[:24] + ".json"
    )


def _build_result_permit(plan, launch, terminal, signature, started_at_utc):
    _utc(started_at_utc, "result read started_at")
    record = {
        "plan_sha256": plan.plan_sha256,
        "launch_sha256": launch.receipt_sha256,
        "terminal_sha256": terminal.receipt_sha256,
        "owner_signature_sha256": _sha(
            signature.authority_sha256, "result signature authority"
        ),
        "started_at_utc": started_at_utc,
        "backtests_read_call_count": 1,
        "ambiguous_result_read_consumes_permit": True,
        "retry_authorized_inside_adapter": False,
    }
    identity, digest, payload = _identified(
        RESULT_PERMIT_SCHEMA, "arv2-preliminary-qc-result-permit-", record
    )
    return AcceptedRiskPreliminaryResultReadPermit(
        identity,
        digest,
        plan.plan_sha256,
        launch.receipt_sha256,
        terminal.receipt_sha256,
        signature.authority_sha256,
        started_at_utc,
        _result_permit_path(plan),
        payload,
    )


def _require_result_permit_bytes(value, plan, launch, terminal):
    if type(value) is not AcceptedRiskPreliminaryResultReadPermit:
        _error("preliminary result-read permit type changed")
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.terminal_sha256 != terminal.receipt_sha256
        or value.permit_path != _result_permit_path(plan)
        or _read_private(value.permit_path, "result-read permit")
        != value.permit_bytes
    ):
        _error("preliminary result-read permit lineage changed")
    raw = _strict_object(value.permit_bytes, "result-read permit")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "owner_signature_sha256", "started_at_utc",
        "backtests_read_call_count", "ambiguous_result_read_consumes_permit",
        "retry_authorized_inside_adapter",
    }:
        _error("preliminary result-read permit fields changed")
    seed = dict(raw)
    declared_id = seed.pop("id")
    declared_sha = seed.pop("sha256")
    seed["id"] = None
    seed["sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        raw.get("schema") != RESULT_PERMIT_SCHEMA
        or raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("launch_sha256") != launch.receipt_sha256
        or raw.get("terminal_sha256") != terminal.receipt_sha256
        or raw.get("owner_signature_sha256") != value.owner_signature_sha256
        or raw.get("started_at_utc") != value.started_at_utc
        or raw.get("backtests_read_call_count") != 1
        or raw.get("ambiguous_result_read_consumes_permit") is not True
        or raw.get("retry_authorized_inside_adapter") is not False
        or declared_id != value.permit_id
        or declared_sha != value.permit_sha256
        or digest != value.permit_sha256
        or value.permit_id != "arv2-preliminary-qc-result-permit-" + digest[:24]
    ):
        _error("preliminary result-read permit identity changed")
    _sha(value.owner_signature_sha256, "result permit owner signature")
    _utc(value.started_at_utc, "result permit started_at")
    return value


def _load_result_permit_impl(
    *, plan, execution_permit, launch, terminal, require_launch, require_terminal,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(execution_permit, plan)
    require_launch(launch, plan, execution_permit)
    require_terminal(terminal, plan, execution_permit, launch)
    path = _result_permit_path(plan)
    payload = _read_private(path, "result-read permit")
    raw = _strict_object(payload, "result-read permit")
    required = {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "owner_signature_sha256", "started_at_utc",
        "backtests_read_call_count", "ambiguous_result_read_consumes_permit",
        "retry_authorized_inside_adapter",
    }
    if set(raw) != required:
        _error("preliminary result-read permit fields changed")
    value = AcceptedRiskPreliminaryResultReadPermit(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["launch_sha256"],
        raw["terminal_sha256"], raw["owner_signature_sha256"],
        raw["started_at_utc"], path, payload,
    )
    return _require_result_permit_bytes(value, plan, launch, terminal)


def _parse_custom_result(response, plan, launch):
    if type(response) is not dict or not set(response).issubset(
        {"success", "errors", "messages", "backtest"}
    ) or response.get("success") is not True:
        _error("preliminary backtests/read envelope changed")
    for key in ("errors", "messages"):
        if key in response and (
            type(response[key]) is not list
            or any(type(item) is not str for item in response[key])
        ):
            _error("preliminary backtests/read message envelope changed")
    backtest = response.get("backtest")
    if type(backtest) is not dict:
        _error("preliminary backtests/read omitted its backtest")
    allowed = _PINNED_BACKTEST_STATUS_KEYS | _PINNED_DISCARDED_BACKTEST_KEYS | {"statistics"}
    if any(type(key) is not str or key not in allowed for key in backtest.keys()):
        _error("preliminary backtests/read backtest envelope changed")
    if (
        backtest.get("backtestId") != launch.backtest_id
        or backtest.get("projectId") != launch.project_id
        or backtest.get("name") != launch.backtest_name
        or backtest.get("status") != "Completed."
    ):
        _error("preliminary backtests/read returned another run")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or any(type(key) is not str for key in statistics):
        _error("preliminary backtests/read omitted exact statistics mapping")
    selected_names = tuple(sorted(key for key in statistics if key.startswith("ARV2_")))
    if selected_names != plan.expected_custom_statistic_names:
        _error("preliminary custom result key inventory changed")
    pairs = []
    parsed = {}
    for name in selected_names:
        value = statistics[name]
        if type(value) is not str or not value or len(value) > 4_096:
            _error("preliminary custom result value exceeded its exact bound")
        try:
            payload = value.encode("ascii")
        except UnicodeError as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary custom result is not ASCII JSON"
            ) from exc
        parsed[name] = _strict_object(payload, "preliminary custom statistic")
        pairs.append((name, value))
    _validate_aggregate_records(parsed, plan)
    return tuple(pairs)


_CELL_FIELDS = frozenset(
    {
        "schema", "source_view_id", "score_arm", "horizon_sessions",
        "window_id", "status", "eligible_score_row_count",
        "accepted_outcome_pair_count", "missing_outcome_pair_count",
        "sector_refused_row_count", "valid_ic_date_count",
        "invalid_ic_date_count", "mean_daily_spearman_ic",
        "median_daily_spearman_ic", "positive_ic_date_share",
        "mean_of_daily_cross_section_mean_excess_returns",
        "median_of_daily_cross_section_mean_excess_returns",
        "outcome_definition", "formal_accept_reject_disposition",
    }
)
_RUNTIME_META_FIELDS = frozenset(
    {
        "schema", "status", "package_id", "package_sha256",
        "activation_manifest_sha256", "symbol_resolution_id",
        "symbol_resolution_sha256", "resolved_security_count",
        "named_security_refusal_count", "training_slice_count",
        "result_transport", "host_object_store_export_required",
        "preliminary", "point_in_time", "formal", "control_residualized",
        "economic_portfolio", "etf_or_leverage", "deployment", "orders",
        "trading",
    }
)
_PRELIMINARY_META_FIELDS = frozenset(
    {
        "schema", "contract_id", "manifest_id", "manifest_sha256", "status",
        "source_lineage_sha256s", "windows", "source_view_ids", "score_arms",
        "horizons", "outcome_definition", "history_normalization_mode",
        "history_value_field", "decay_state_method", "benchmark_role",
        "q_data_policy_id", "input_security_count", "input_contribution_count",
        "completed_callback_count", "accepted_risk_disclosures",
        "omitted_formal_components", "raw_provider_rows_in_summary",
        "raw_security_outcome_rows_in_summary", "raw_price_rows_in_summary",
        "formal_result", "alpha_claim_authorized", "summary_id",
        "summary_sha256",
    }
)
_CELL_COUNT_FIELDS = (
    "eligible_score_row_count",
    "accepted_outcome_pair_count",
    "missing_outcome_pair_count",
    "sector_refused_row_count",
    "valid_ic_date_count",
    "invalid_ic_date_count",
)
_CELL_METRIC_FIELDS = (
    "mean_daily_spearman_ic",
    "median_daily_spearman_ic",
    "positive_ic_date_share",
    "mean_of_daily_cross_section_mean_excess_returns",
    "median_of_daily_cross_section_mean_excess_returns",
)
_DECIMAL_METRIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


def _authenticated_evaluator_manifest(plan) -> dict[str, object]:
    observed = None
    for descriptor, payload in _PINNED_ITER_UPLOADS(plan.package):
        if descriptor.role != "evaluator_manifest":
            continue
        if observed is not None or not payload.endswith(b"\n"):
            _error("authenticated evaluator manifest inventory changed")
        observed = _strict_object(payload[:-1], "authenticated evaluator manifest")
    if (
        type(observed) is not dict
        or observed.get("manifest_id") != plan.evaluator_manifest_id
        or observed.get("manifest_sha256") != plan.evaluator_manifest_sha256
    ):
        _error("authenticated evaluator manifest lineage changed")
    return observed


def _cell_metric(value: object, name: str) -> Decimal:
    if type(value) is not str or _DECIMAL_METRIC.fullmatch(value) is None:
        _error(f"preliminary {name} is not canonical finite Decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise AcceptedRiskPreliminarySubmissionError(
            f"preliminary {name} is not canonical finite Decimal text"
        ) from exc
    if (
        not parsed.is_finite()
        or format(parsed, "f") != value
        or (parsed == 0 and value != "0")
    ):
        _error(f"preliminary {name} is not canonical finite Decimal text")
    return parsed


def _validate_cell_semantics(record: dict[str, object]) -> int:
    if any(
        type(record.get(name)) is not int or record[name] < 0
        for name in _CELL_COUNT_FIELDS
    ):
        _error("preliminary aggregate cell count changed")
    eligible = record["eligible_score_row_count"]
    accepted = record["accepted_outcome_pair_count"]
    missing = record["missing_outcome_pair_count"]
    sector_refused = record["sector_refused_row_count"]
    valid = record["valid_ic_date_count"]
    invalid = record["invalid_ic_date_count"]
    if (
        eligible != accepted + missing
        or accepted < valid * preliminary_evaluator.MINIMUM_IC_ROWS
        or (sector_refused > 0 and invalid == 0)
    ):
        _error("preliminary aggregate cell count invariants changed")
    expected_status = (
        "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
        if valid >= 50
        else "INCONCLUSIVE_UNDERFILLED"
    )
    if record.get("status") != expected_status:
        _error("preliminary aggregate cell status changed")
    metrics = tuple(record.get(name) for name in _CELL_METRIC_FIELDS)
    if valid == 0:
        if any(value is not None for value in metrics):
            _error("preliminary aggregate cell unavailable metrics changed")
    else:
        if any(value is None for value in metrics):
            _error("preliminary aggregate cell available metrics changed")
        parsed = tuple(
            _cell_metric(value, name)
            for name, value in zip(_CELL_METRIC_FIELDS, metrics, strict=True)
        )
        if (
            not Decimal("-1") <= parsed[0] <= Decimal("1")
            or not Decimal("-1") <= parsed[1] <= Decimal("1")
            or not Decimal("0") <= parsed[2] <= Decimal("1")
        ):
            _error("preliminary aggregate cell bounded metric changed")
    return valid + invalid


def _validate_aggregate_records(records: Mapping[str, dict[str, object]], plan) -> None:
    authenticated_manifest = _authenticated_evaluator_manifest(plan)
    runtime_meta = records.get("ARV2_RUNTIME_META")
    preliminary_meta = records.get("ARV2_PRELIMINARY_META")
    if type(runtime_meta) is not dict or type(preliminary_meta) is not dict:
        _error("preliminary aggregate metadata is absent")
    if (
        set(runtime_meta) != _RUNTIME_META_FIELDS
        or set(preliminary_meta) != _PRELIMINARY_META_FIELDS
        or runtime_meta.get("schema")
        != "arv2-accepted-risk-preliminary-qc-runtime-meta-v1"
        or runtime_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY_COMPLETED"
        or runtime_meta.get("package_id") != plan.package_id
        or runtime_meta.get("package_sha256") != plan.package_sha256
        or runtime_meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or runtime_meta.get("result_transport")
        != "aggregate_only_custom_summary_statistics"
        or _safe_name(
            runtime_meta.get("symbol_resolution_id"),
            "preliminary symbol resolution id",
            512,
        )
        != runtime_meta.get("symbol_resolution_id")
        or _sha(
            runtime_meta.get("symbol_resolution_sha256"),
            "preliminary symbol resolution",
        )
        != runtime_meta.get("symbol_resolution_sha256")
        or runtime_meta.get("host_object_store_export_required") is not False
        or runtime_meta.get("preliminary") is not True
        or any(
            runtime_meta.get(name) is not False
            for name in (
                "point_in_time", "formal", "control_residualized",
                "economic_portfolio", "etf_or_leverage", "deployment",
                "orders", "trading",
            )
        )
        or type(runtime_meta.get("resolved_security_count")) is not int
        or type(runtime_meta.get("named_security_refusal_count")) is not int
        or runtime_meta["resolved_security_count"] < 0
        or runtime_meta["named_security_refusal_count"] < 0
        or runtime_meta["resolved_security_count"]
        + runtime_meta["named_security_refusal_count"]
        != plan.package.runtime_symbol_binding_count
        or type(runtime_meta.get("training_slice_count")) is not int
        or not 1 <= runtime_meta["training_slice_count"]
        <= preliminary_runtime.MAX_TRAIN_SLICE_COUNT
    ):
        _error("preliminary runtime aggregate metadata changed")
    cells_by_axis = {}
    date_geometry: dict[str, set[int]] = {}
    score_geometry: dict[tuple[str, str], set[tuple[int, int]]] = {}
    for name, record in records.items():
        match = _CELL_NAME.fullmatch(name)
        if match is None:
            continue
        if type(record) is not dict or set(record) != _CELL_FIELDS:
            _error("preliminary aggregate cell fields changed")
        view_token, arm_token, horizon_text, window_token = match.groups()
        expected_view = preliminary_evaluator.SOURCE_VIEW_IDS[
            0 if view_token == "CUR" else 1
        ]
        expected_arm = "firm_specific" if arm_token == "FIRM" else "global_comparator"
        expected_horizon = int(horizon_text)
        expected_window = (
            preliminary_evaluator.PRIMARY_WINDOW["window_id"]
            if window_token == "2020_2025"
            else preliminary_evaluator.DESCRIPTIVE_WINDOW["window_id"]
        )
        if (
            record.get("schema") != preliminary_evaluator.CELL_SCHEMA
            or record.get("source_view_id") != expected_view
            or record.get("score_arm") != expected_arm
            or record.get("horizon_sessions") != expected_horizon
            or record.get("window_id") != expected_window
            or record.get("outcome_definition")
            != preliminary_evaluator.HISTORY_OBSERVATION
            or record.get("formal_accept_reject_disposition") is not None
        ):
            _error("preliminary aggregate cell axis changed")
        date_geometry.setdefault(expected_window, set()).add(
            _validate_cell_semantics(record)
        )
        score_geometry.setdefault((expected_window, expected_view), set()).add(
            (
                record["eligible_score_row_count"],
                record["sector_refused_row_count"],
            )
        )
        cells_by_axis[(expected_window, expected_view, expected_arm, expected_horizon)] = record
    expected_axes = tuple(
        (window["window_id"], view, arm, horizon)
        for window in preliminary_evaluator.WINDOWS
        for view in preliminary_evaluator.SOURCE_VIEW_IDS
        for arm in preliminary_evaluator.SCORE_ARMS
        for horizon in preliminary_evaluator.HORIZONS
    )
    if set(cells_by_axis) != set(expected_axes):
        _error("preliminary aggregate cell inventory changed")
    if any(len(values) != 1 for values in date_geometry.values()) or any(
        len(values) != 1 for values in score_geometry.values()
    ):
        _error("preliminary aggregate cell geometry changed")
    if (
        preliminary_meta.get("schema") != preliminary_evaluator.SUMMARY_SCHEMA
        or preliminary_meta.get("contract_id") != preliminary_evaluator.CONTRACT_ID
        or preliminary_meta.get("manifest_id") != plan.evaluator_manifest_id
        or preliminary_meta.get("manifest_sha256") != plan.evaluator_manifest_sha256
        or preliminary_meta.get("status")
        != "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY"
        or preliminary_meta.get("windows")
        != [dict(item) for item in preliminary_evaluator.WINDOWS]
        or preliminary_meta.get("source_view_ids")
        != list(preliminary_evaluator.SOURCE_VIEW_IDS)
        or preliminary_meta.get("score_arms")
        != list(preliminary_evaluator.SCORE_ARMS)
        or preliminary_meta.get("horizons")
        != list(preliminary_evaluator.HORIZONS)
        or preliminary_meta.get("outcome_definition")
        != preliminary_evaluator.HISTORY_OBSERVATION
        or preliminary_meta.get("history_normalization_mode") != "TOTAL_RETURN"
        or preliminary_meta.get("history_value_field") != "open"
        or preliminary_meta.get("decay_state_method")
        != (
            "sparse_positive_common_scale_mathematically_equivalent_"
            "not_byte_identical_to_formal_per_event_replay"
        )
        or preliminary_meta.get("benchmark_role")
        != "matching_SPY_open_to_open_total_return"
        or preliminary_meta.get("q_data_policy_id")
        != preliminary_evaluator.Q_DATA_POLICY_ID
        or preliminary_meta.get("accepted_risk_disclosures")
        != dict(preliminary_evaluator.ACCEPTED_RISK_DISCLOSURES)
        or preliminary_meta.get("omitted_formal_components")
        != list(preliminary_evaluator.OMITTED_FORMAL_COMPONENTS)
        or any(
            type(preliminary_meta.get(name)) is not int
            or preliminary_meta[name] < 0
            for name in (
                "input_security_count", "input_contribution_count",
                "completed_callback_count",
            )
        )
        or preliminary_meta.get("input_security_count")
        != plan.package.runtime_symbol_binding_count
        or preliminary_meta.get("input_contribution_count")
        != authenticated_manifest.get("contribution_row_count")
        or preliminary_meta.get("completed_callback_count") == 0
        or preliminary_meta.get("formal_result") is not False
        or preliminary_meta.get("alpha_claim_authorized") is not False
        or any(
            preliminary_meta.get(name) is not False
            for name in (
                "raw_provider_rows_in_summary",
                "raw_security_outcome_rows_in_summary",
                "raw_price_rows_in_summary",
            )
        )
    ):
        _error("preliminary evaluator aggregate metadata changed")
    lineage = preliminary_meta.get("source_lineage_sha256s")
    if (
        type(lineage) is not dict
        or set(lineage) != set(preliminary_evaluator._SOURCE_LINEAGE_FIELDS)
        or any(_sha(lineage[name], name) != lineage[name] for name in lineage)
        or lineage != authenticated_manifest.get("source_lineage_sha256s")
    ):
        _error("preliminary evaluator source lineage changed")
    summary_id = preliminary_meta.get("summary_id")
    summary_sha = preliminary_meta.get("summary_sha256")
    if type(summary_id) is not str or type(summary_sha) is not str:
        _error("preliminary evaluator summary identity is absent")
    record = {
        key: value
        for key, value in preliminary_meta.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    record["cells"] = [cells_by_axis[axis] for axis in expected_axes]
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if summary_sha != digest or summary_id != "arv2-preliminary-rating-summary-" + digest[:24]:
        _error("preliminary evaluator summary identity changed")


def _result_receipt_path(plan):
    return plan.control_directory / (
        "aggregate-result-" + plan.plan_sha256[:24] + ".json"
    )


def _load_result_receipt_impl(
    *, plan, execution_permit, launch, terminal, result_permit,
    require_launch, require_terminal, register_result,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(execution_permit, plan)
    require_launch(launch, plan, execution_permit)
    require_terminal(terminal, plan, execution_permit, launch)
    _require_result_permit_bytes(result_permit, plan, launch, terminal)
    path = _result_receipt_path(plan)
    payload = _read_private(path, "aggregate result receipt")
    raw = _strict_object(payload, "aggregate result receipt")
    if set(raw) != {
        "schema", "id", "sha256", "plan_sha256", "launch_sha256",
        "terminal_sha256", "result_permit_sha256", "project_id",
        "backtest_id", "custom_statistics", "custom_statistics_sha256",
        "persisted_path", "backtests_read_call_count",
        "raw_provider_rows_selected", "logs_selected", "charts_selected",
        "orders_selected", "look_accounting",
    }:
        _error("preliminary aggregate result receipt fields changed")
    raw_pairs = raw.get("custom_statistics")
    if (
        type(raw_pairs) is not list
        or type(raw.get("persisted_path")) is not str
        or any(
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            for item in raw_pairs
        )
    ):
        _error("preliminary persisted custom statistics changed")
    pairs = tuple((item[0], item[1]) for item in raw_pairs)
    if tuple(name for name, _value in pairs) != plan.expected_custom_statistic_names:
        _error("preliminary persisted custom-statistic inventory changed")
    records: dict[str, dict[str, object]] = {}
    for name, value in pairs:
        try:
            encoded = value.encode("ascii")
        except UnicodeError as exc:
            raise AcceptedRiskPreliminarySubmissionError(
                "preliminary persisted custom statistic is not ASCII"
            ) from exc
        if not encoded or len(encoded) > 4096:
            _error("preliminary persisted custom statistic is not bounded")
        records[name] = _strict_object(encoded, f"persisted custom statistic {name}")
    _validate_aggregate_records(records, plan)
    pairs_hash = hashlib.sha256(
        _canonical([list(item) for item in pairs])
    ).hexdigest()
    value = AcceptedRiskPreliminaryAggregateResult(
        raw["id"], raw["sha256"], raw["plan_sha256"], raw["launch_sha256"],
        raw["terminal_sha256"], raw["result_permit_sha256"],
        raw["project_id"], raw["backtest_id"], pairs,
        raw["custom_statistics_sha256"], Path(raw["persisted_path"]),
        raw["backtests_read_call_count"], raw["raw_provider_rows_selected"],
        raw["logs_selected"], raw["charts_selected"], raw["orders_selected"],
    )
    if (
        value.plan_sha256 != plan.plan_sha256
        or value.launch_sha256 != launch.receipt_sha256
        or value.terminal_sha256 != terminal.receipt_sha256
        or value.result_permit_sha256 != result_permit.permit_sha256
        or raw.get("look_accounting") != _look_accounting(stage="result")
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or value.custom_statistics_sha256 != pairs_hash
        or value.persisted_path != path
        or value.backtests_read_call_count != 1
        or value.raw_provider_rows_selected is not False
        or value.logs_selected is not False
        or value.charts_selected is not False
        or value.orders_selected is not False
        or payload != _identified_receipt_bytes(
            schema=RESULT_RECEIPT_SCHEMA,
            prefix="arv2-preliminary-qc-result-",
            record=_result_record(value),
            receipt_id=value.receipt_id,
            receipt_sha256=value.receipt_sha256,
        )
    ):
        _error("preliminary aggregate result receipt lineage changed")
    register_result(
        value, plan, execution_permit, launch, terminal, result_permit
    )
    return value


def _read_accepted_risk_preliminary_result_once_impl(
    *, plan, owner_signature, execution_permit, launch, terminal, client,
    started_at_utc, minter, signature_verifier, transport_verifier, require_launch,
    require_terminal, register_result,
):
    plan = require_accepted_risk_preliminary_submission_plan(plan)
    _require_execution_permit_bytes(execution_permit, plan)
    require_launch(launch, plan, execution_permit)
    require_terminal(terminal, plan, execution_permit, launch)
    authority = _result_authority_bound(
        plan, execution_permit, launch, terminal, require_launch, require_terminal
    )
    signature = signature_verifier(owner_signature, authority)
    if terminal.terminal_status != "Completed.":
        _error("preliminary result read requires Completed.")
    transport_verifier(client)
    result_permit = _build_result_permit(
        plan, launch, terminal, signature, started_at_utc
    )
    try:
        _write_private_once(
            result_permit.permit_path,
            result_permit.permit_bytes,
            "result-read permit",
        )
    except AcceptedRiskPreliminarySubmissionError as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "result_read_permit", result_permit.permit_id,
            "permit already spent or unavailable",
        ) from exc
    _require_result_permit_bytes(result_permit, plan, launch, terminal)
    capability = minter(
        transport=client,
        scope="result_read",
        binding_record={
            "schema": "arv2-accepted-risk-preliminary-result-read-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "launch_sha256": launch.receipt_sha256,
            "terminal_sha256": terminal.receipt_sha256,
            "result_permit_sha256": result_permit.permit_sha256,
            "expected_custom_statistic_names_sha256": (
                plan.expected_custom_statistic_names_sha256
            ),
        },
        call_budget={"backtests/read": 1},
    )
    try:
        response = _transport(
            client,
            capability,
            "_read_backtest_result",
            launch.project_id,
            launch.backtest_id,
        )
        pairs = _parse_custom_result(response, plan, launch)
        pairs_hash = hashlib.sha256(
            _canonical([list(item) for item in pairs])
        ).hexdigest()
        path = _result_receipt_path(plan)
        record = {
            "plan_sha256": plan.plan_sha256,
            "launch_sha256": launch.receipt_sha256,
            "terminal_sha256": terminal.receipt_sha256,
            "result_permit_sha256": result_permit.permit_sha256,
            "look_accounting": _look_accounting(stage="result"),
            "project_id": launch.project_id,
            "backtest_id": launch.backtest_id,
            "custom_statistics": [list(item) for item in pairs],
            "custom_statistics_sha256": pairs_hash,
            "persisted_path": str(path),
            "backtests_read_call_count": 1,
            "raw_provider_rows_selected": False,
            "logs_selected": False,
            "charts_selected": False,
            "orders_selected": False,
        }
        identity, digest, payload = _identified(
            RESULT_RECEIPT_SCHEMA, "arv2-preliminary-qc-result-", record
        )
        _write_private_once(path, payload, "aggregate result receipt")
        result = AcceptedRiskPreliminaryAggregateResult(
            identity,
            digest,
            plan.plan_sha256,
            launch.receipt_sha256,
            terminal.receipt_sha256,
            result_permit.permit_sha256,
            launch.project_id,
            launch.backtest_id,
            pairs,
            pairs_hash,
            path,
            1,
            False,
            False,
            False,
            False,
        )
        register_result(
            result, plan, execution_permit, launch, terminal, result_permit
        )
        return result_permit, result
    except AcceptedRiskPreliminarySubmissionLocked:
        raise
    except Exception as exc:
        raise AcceptedRiskPreliminarySubmissionLocked(
            "result_read", result_permit.permit_id, type(exc).__name__
        ) from exc


def _result_authority_bound(plan, permit, launch, terminal, require_launch, require_terminal):
    require_launch(launch, plan, permit)
    require_terminal(terminal, plan, permit, launch)
    if terminal.terminal_status != "Completed.":
        _error("preliminary result-read authority requires Completed.")
    return _canonical(
        {
            "schema": RESULT_AUTHORITY_SCHEMA,
            "signature_purpose": "formal_qc_result_read",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "package_id": plan.package_id,
            "package_sha256": plan.package_sha256,
            "evaluator_manifest_id": plan.evaluator_manifest_id,
            "evaluator_manifest_sha256": plan.evaluator_manifest_sha256,
            "projection_id": plan.projection_id,
            "projection_sha256": plan.projection_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
            "terminal_receipt_sha256": terminal.receipt_sha256,
            "project_id": launch.project_id,
            "backtest_id": launch.backtest_id,
            "terminal_status": terminal.terminal_status,
            "expected_custom_statistic_names": list(plan.expected_custom_statistic_names),
            "expected_custom_statistic_names_sha256": plan.expected_custom_statistic_names_sha256,
            "host_code_closure": _require_host_closure(
                plan.host_closure
            ).to_record(),
            "look_accounting": _look_accounting(stage="launch"),
            "actions": list(RESULT_ACTIONS),
            "maximum_backtests_read_calls": 1,
            "raw_provider_price_rows_logs_charts_orders_selected": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
    )


def _make_action_guard():
    expected: tuple[tuple[str, object], ...] = ()
    authority_pid = os.getpid()
    module_globals = globals()

    def seal(names: tuple[str, ...]) -> None:
        nonlocal expected
        if expected or type(names) is not tuple or not names:
            _error("preliminary action binding seal changed")
        expected = tuple((name, module_globals[name]) for name in names)

    def require(_phase: str) -> None:
        if os.getpid() != authority_pid or any(
            module_globals.get(name) is not value for name, value in expected
        ):
            _error("preliminary action global binding changed")

    return seal, require


_seal_action_bindings, _require_action_bindings = _make_action_guard()
del _make_action_guard


def _bind_public_actions(
    *, minter, seal_minter, execute_impl, recover_impl, inspect_impl, read_impl,
    load_launch_impl, load_terminal_impl, load_result_permit_impl,
    load_result_receipt_impl,
    execution_signature_verifier, result_signature_verifier,
    transport_verifier,
    action_guard, register_launch, require_launch, register_terminal,
    require_terminal, register_result, require_result,
):
    def execute_accepted_risk_preliminary_submission_once(
        *, plan: AcceptedRiskPreliminarySubmissionPlan,
        owner_signature: OwnerSignatureAuthority | None,
        client: FormalQcTransport,
        started_at_utc: str,
    ):
        action_guard("submission")
        return execute_impl(
            plan=plan,
            owner_signature=owner_signature,
            client=client,
            started_at_utc=started_at_utc,
            minter=minter,
            signature_verifier=execution_signature_verifier,
            transport_verifier=transport_verifier,
            register_launch=register_launch,
        )

    def require_accepted_risk_preliminary_launch_receipt(value, *, plan, permit):
        action_guard("launch require")
        return require_launch(value, plan, permit)

    def load_accepted_risk_preliminary_launch_receipt(*, plan, permit):
        action_guard("launch load")
        return load_launch_impl(
            plan=plan,
            permit=permit,
            register_launch=register_launch,
        )

    def recover_accepted_risk_preliminary_launch_once(
        *, plan, owner_signature, permit, client,
    ):
        action_guard("launch recovery")
        return recover_impl(
            plan=plan,
            owner_signature=owner_signature,
            permit=permit,
            client=client,
            minter=minter,
            signature_verifier=execution_signature_verifier,
            transport_verifier=transport_verifier,
            load_launch=load_launch_impl,
            register_launch=register_launch,
        )

    def inspect_accepted_risk_preliminary_terminal_status(
        *, plan, owner_signature, permit, launch, client,
    ):
        action_guard("status")
        return inspect_impl(
            plan=plan,
            owner_signature=owner_signature,
            permit=permit,
            launch=launch,
            client=client,
            minter=minter,
            signature_verifier=execution_signature_verifier,
            transport_verifier=transport_verifier,
            require_launch=require_launch,
            register_terminal=register_terminal,
        )

    def require_accepted_risk_preliminary_terminal_status(
        value, *, plan, permit, launch,
    ):
        action_guard("terminal require")
        return require_terminal(value, plan, permit, launch)

    def load_accepted_risk_preliminary_terminal_status(
        *, plan, permit, launch,
    ):
        action_guard("terminal load")
        return load_terminal_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            require_launch=require_launch,
            register_terminal=register_terminal,
        )

    def render_accepted_risk_preliminary_result_read_authority_candidate(
        *, plan, permit, launch, terminal,
    ) -> bytes:
        action_guard("result authority")
        return _result_authority_bound(
            plan, permit, launch, terminal, require_launch, require_terminal
        )

    def load_accepted_risk_preliminary_result_read_permit(
        *, plan, execution_permit, launch, terminal,
    ):
        action_guard("result permit load")
        return load_result_permit_impl(
            plan=plan,
            execution_permit=execution_permit,
            launch=launch,
            terminal=terminal,
            require_launch=require_launch,
            require_terminal=require_terminal,
        )

    def require_accepted_risk_preliminary_result_read_permit(
        value, *, plan, execution_permit, launch, terminal,
    ):
        action_guard("result permit require")
        plan = require_accepted_risk_preliminary_submission_plan(plan)
        _require_execution_permit_bytes(execution_permit, plan)
        require_launch(launch, plan, execution_permit)
        require_terminal(terminal, plan, execution_permit, launch)
        return _require_result_permit_bytes(value, plan, launch, terminal)

    def read_accepted_risk_preliminary_result_once(
        *, plan, execution_permit, launch, terminal,
        owner_signature, client, started_at_utc,
    ):
        action_guard("result read")
        return read_impl(
            plan=plan,
            owner_signature=owner_signature,
            execution_permit=execution_permit,
            launch=launch,
            terminal=terminal,
            client=client,
            started_at_utc=started_at_utc,
            minter=minter,
            signature_verifier=result_signature_verifier,
            transport_verifier=transport_verifier,
            require_launch=require_launch,
            require_terminal=require_terminal,
            register_result=register_result,
        )

    def require_accepted_risk_preliminary_aggregate_result(
        value, *, plan, execution_permit, launch, terminal, result_permit,
    ):
        action_guard("result require")
        if type(value) is not AcceptedRiskPreliminaryAggregateResult:
            _error("preliminary result receipt type changed")
        if _read_private(value.persisted_path, "aggregate result receipt") != _canonical(
            {
                "schema": RESULT_RECEIPT_SCHEMA,
                "id": value.receipt_id,
                "sha256": value.receipt_sha256,
                **_result_record(value),
            }
        ):
            _error("persisted preliminary aggregate result changed")
        return require_result(
            value, plan, execution_permit, launch, terminal, result_permit
        )

    def load_accepted_risk_preliminary_aggregate_result(
        *, plan, execution_permit, launch, terminal, result_permit,
    ):
        action_guard("result load")
        return load_result_receipt_impl(
            plan=plan,
            execution_permit=execution_permit,
            launch=launch,
            terminal=terminal,
            result_permit=result_permit,
            require_launch=require_launch,
            require_terminal=require_terminal,
            register_result=register_result,
        )

    seal_minter(
        (
            (
                "submission",
                ((execute_impl, execute_accepted_risk_preliminary_submission_once),),
            ),
            (
                "status",
                (
                    (inspect_impl, inspect_accepted_risk_preliminary_terminal_status),
                    (recover_impl, recover_accepted_risk_preliminary_launch_once),
                ),
            ),
            (
                "result_read",
                ((read_impl, read_accepted_risk_preliminary_result_once),),
            ),
        )
    )
    return (
        execute_accepted_risk_preliminary_submission_once,
        require_accepted_risk_preliminary_launch_receipt,
        load_accepted_risk_preliminary_launch_receipt,
        recover_accepted_risk_preliminary_launch_once,
        inspect_accepted_risk_preliminary_terminal_status,
        require_accepted_risk_preliminary_terminal_status,
        load_accepted_risk_preliminary_terminal_status,
        render_accepted_risk_preliminary_result_read_authority_candidate,
        load_accepted_risk_preliminary_result_read_permit,
        require_accepted_risk_preliminary_result_read_permit,
        read_accepted_risk_preliminary_result_once,
        require_accepted_risk_preliminary_aggregate_result,
        load_accepted_risk_preliminary_aggregate_result,
    )


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = formal._claim_accepted_risk_preliminary_transport_capability_minter()

(
    execute_accepted_risk_preliminary_submission_once,
    require_accepted_risk_preliminary_launch_receipt,
    load_accepted_risk_preliminary_launch_receipt,
    recover_accepted_risk_preliminary_launch_once,
    inspect_accepted_risk_preliminary_terminal_status,
    require_accepted_risk_preliminary_terminal_status,
    load_accepted_risk_preliminary_terminal_status,
    render_accepted_risk_preliminary_result_read_authority_candidate,
    load_accepted_risk_preliminary_result_read_permit,
    require_accepted_risk_preliminary_result_read_permit,
    read_accepted_risk_preliminary_result_once,
    require_accepted_risk_preliminary_aggregate_result,
    load_accepted_risk_preliminary_aggregate_result,
) = _bind_public_actions(
    minter=_transport_capability_minter,
    seal_minter=_seal_transport_capability_callers,
    execute_impl=_execute_accepted_risk_preliminary_submission_once_impl,
    recover_impl=_recover_accepted_risk_preliminary_launch_once_impl,
    inspect_impl=_inspect_accepted_risk_preliminary_terminal_status_impl,
    read_impl=_read_accepted_risk_preliminary_result_once_impl,
    load_launch_impl=_load_launch_receipt_impl,
    load_terminal_impl=_load_terminal_receipt_impl,
    load_result_permit_impl=_load_result_permit_impl,
    load_result_receipt_impl=_load_result_receipt_impl,
    execution_signature_verifier=_require_execution_signature,
    result_signature_verifier=_require_result_signature,
    transport_verifier=_PINNED_REQUIRE_TRANSPORT,
    action_guard=_require_action_bindings,
    register_launch=_register_launch,
    require_launch=_require_launch,
    register_terminal=_register_terminal,
    require_terminal=_require_terminal,
    register_result=_register_result,
    require_result=_require_result,
)

_seal_action_bindings(
    (
        "build_accepted_risk_preliminary_submission_plan",
        "require_accepted_risk_preliminary_submission_plan",
        "persist_accepted_risk_preliminary_submission_plan",
        "load_accepted_risk_preliminary_submission_plan",
        "render_accepted_risk_preliminary_execution_authority_candidate",
        "execute_accepted_risk_preliminary_submission_once",
        "load_accepted_risk_preliminary_submission_permit",
        "load_accepted_risk_preliminary_pre_create_control",
        "require_accepted_risk_preliminary_launch_receipt",
        "load_accepted_risk_preliminary_launch_receipt",
        "recover_accepted_risk_preliminary_launch_once",
        "inspect_accepted_risk_preliminary_terminal_status",
        "require_accepted_risk_preliminary_terminal_status",
        "load_accepted_risk_preliminary_terminal_status",
        "render_accepted_risk_preliminary_result_read_authority_candidate",
        "load_accepted_risk_preliminary_result_read_permit",
        "require_accepted_risk_preliminary_result_read_permit",
        "read_accepted_risk_preliminary_result_once",
        "require_accepted_risk_preliminary_aggregate_result",
        "load_accepted_risk_preliminary_aggregate_result",
        "_PINNED_REQUIRE_PACKAGE",
        "_PINNED_ITER_UPLOADS",
        "_PINNED_REQUIRE_PROJECTION",
        "_PINNED_EXPECTED_RESULT_NAMES",
        "_PINNED_REQUIRE_EXECUTION_SIGNATURE",
        "_PINNED_REQUIRE_RESULT_SIGNATURE",
        "_PINNED_LOAD_INFRASTRUCTURE_LEDGER",
        "_PINNED_REQUIRE_INFRASTRUCTURE_LEDGER",
        "_PINNED_INFRASTRUCTURE_LEDGER",
        "_PINNED_REQUIRE_TRANSPORT",
        "_PINNED_TRANSPORT_CALL",
        "_PINNED_READ_PROJECTS",
        "_PINNED_PROJECT_RECORD",
        "_PINNED_CREATED_PROJECT",
        "_PINNED_READ_FILES",
        "_PINNED_SUCCESS",
        "_PINNED_OBJECT_METADATA",
        "_PINNED_COMPILE_ID",
        "_PINNED_COMPILE_STATE",
        "_PINNED_CREATED_BACKTEST",
        "_PINNED_PARSE_STATUS",
        "_PINNED_PARSE_UNIQUE_RUN",
        "_PINNED_LEXISTS",
        "_PINNED_SCANDIR",
        "_PINNED_BACKTEST_STATUS_KEYS",
        "_PINNED_DISCARDED_BACKTEST_KEYS",
        "_PINNED_COMPILE_TERMINAL_STATES",
        "_PINNED_BACKTEST_TERMINAL_STATES",
        "PLAN_SCHEMA",
        "EXECUTION_AUTHORITY_SCHEMA",
        "EXECUTION_PERMIT_SCHEMA",
        "PRECREATE_CONTROL_SCHEMA",
        "LAUNCH_RECOVERY_PERMIT_SCHEMA",
        "LAUNCH_SCHEMA",
        "TERMINAL_SCHEMA",
        "RESULT_AUTHORITY_SCHEMA",
        "RESULT_PERMIT_SCHEMA",
        "RESULT_RECEIPT_SCHEMA",
        "UPLOAD_ENTRY_SCHEMA",
        "HOST_CLOSURE_SCHEMA",
        "MAX_CONTROL_BYTES",
        "MAX_HOST_SOURCE_BYTES",
        "MAX_PROJECT_NAME_BYTES",
        "MAX_BACKTEST_NAME_BYTES",
        "MAX_COMPILE_POLLS",
        "MAX_STATUS_POLLS",
        "COMPILE_POLL_SECONDS",
        "STATUS_POLL_SECONDS",
        "QC_DEFAULT_RESEARCH_NOTEBOOK_PATH",
        "RECOVERED_LAUNCH_INITIAL_STATUS",
        "HOST_CODE_DIRECTORY_PATHS",
        "HOST_CODE_PATHS",
        "EXECUTION_ACTIONS",
        "RESULT_ACTIONS",
        "_HEX",
        "_SAFE_NAME",
        "_CELL_NAME",
        "_CELL_FIELDS",
        "_RUNTIME_META_FIELDS",
        "_PRELIMINARY_META_FIELDS",
        "_CELL_COUNT_FIELDS",
        "_CELL_METRIC_FIELDS",
        "_DECIMAL_METRIC",
        "AcceptedRiskPreliminarySubmissionError",
        "AcceptedRiskPreliminarySubmissionLocked",
        "AcceptedRiskPreliminaryTerminalFailure",
        "AcceptedRiskPreliminaryHostSourceBinding",
        "AcceptedRiskPreliminaryHostClosureBinding",
        "AcceptedRiskPreliminaryUploadEntry",
        "AcceptedRiskPreliminarySubmissionPlan",
        "AcceptedRiskPreliminarySubmissionPermit",
        "AcceptedRiskPreliminaryPreCreateControl",
        "AcceptedRiskPreliminaryLaunchReceipt",
        "AcceptedRiskPreliminaryTerminalStatus",
        "AcceptedRiskPreliminaryResultReadPermit",
        "AcceptedRiskPreliminaryAggregateResult",
        "_error",
        "_canonical",
        "_strict_object",
        "_sha",
        "_safe_name",
        "_utc",
        "_private_directory",
        "_read_private",
        "_write_private_once",
        "_identified",
        "_read_host_source",
        "_walk_host_python_sources",
        "_host_code_inventory_paths",
        "_build_host_closure",
        "_require_host_closure",
        "_upload_entries",
        "_plan_record",
        "_submission_plan_path",
        "_submission_plan_bytes",
        "_execution_authority",
        "_require_execution_signature",
        "_require_result_signature",
        "_execution_permit_path",
        "_build_execution_permit",
        "_spend_execution_permit",
        "_require_execution_permit_bytes",
        "_precreate_control_path",
        "_build_precreate_control",
        "_require_precreate_control",
        "_launch_recovery_permit_path",
        "_launch_recovery_permit_record",
        "_spend_launch_recovery_permit",
        "_require_launch_recovery_permit",
        "_launch_record",
        "_terminal_record",
        "_result_record",
        "_launch_receipt_path",
        "_terminal_receipt_path",
        "_identified_receipt_bytes",
        "_launch_receipt_bytes",
        "_terminal_receipt_bytes",
        "_wait",
        "_transport",
        "_new_launch",
        "_new_terminal",
        "_result_permit_path",
        "_build_result_permit",
        "_require_result_permit_bytes",
        "_parse_custom_result",
        "_authenticated_evaluator_manifest",
        "_cell_metric",
        "_validate_cell_semantics",
        "_validate_aggregate_records",
        "_result_receipt_path",
        "_result_authority_bound",
        "_look_accounting",
        "dataclasses",
        "hashlib",
        "json",
        "os",
        "re",
        "stat",
        "threading",
        "time",
        "weakref",
        "datetime",
        "timezone",
        "Decimal",
        "InvalidOperation",
        "Path",
        "package_builder",
        "projection_builder",
        "preregistration",
        "preliminary_runtime",
        "preliminary_evaluator",
        "formal",
        "FormalQcTransport",
        "OwnerSignatureAuthority",
        "OwnerSignatureAuthorityError",
    )
)

del _transport_capability_minter
del _seal_transport_capability_callers
del _bind_public_actions
del _execute_accepted_risk_preliminary_submission_once_impl
del _recover_accepted_risk_preliminary_launch_once_impl
del _inspect_accepted_risk_preliminary_terminal_status_impl
del _read_accepted_risk_preliminary_result_once_impl
del _load_launch_receipt_impl
del _load_terminal_receipt_impl
del _load_result_permit_impl
del _load_result_receipt_impl
del _register_launch
del _require_launch
del _register_terminal
del _require_terminal
del _register_result
del _require_result
del _seal_action_bindings
del _require_action_bindings


__all__ = (
    "AcceptedRiskPreliminaryAggregateResult",
    "AcceptedRiskPreliminaryHostClosureBinding",
    "AcceptedRiskPreliminaryHostSourceBinding",
    "AcceptedRiskPreliminaryLaunchReceipt",
    "AcceptedRiskPreliminaryPreCreateControl",
    "AcceptedRiskPreliminaryResultReadPermit",
    "AcceptedRiskPreliminarySubmissionError",
    "AcceptedRiskPreliminarySubmissionLocked",
    "AcceptedRiskPreliminarySubmissionPermit",
    "AcceptedRiskPreliminarySubmissionPlan",
    "AcceptedRiskPreliminaryTerminalFailure",
    "AcceptedRiskPreliminaryTerminalStatus",
    "AcceptedRiskPreliminaryUploadEntry",
    "build_accepted_risk_preliminary_submission_plan",
    "execute_accepted_risk_preliminary_submission_once",
    "inspect_accepted_risk_preliminary_terminal_status",
    "load_accepted_risk_preliminary_aggregate_result",
    "load_accepted_risk_preliminary_launch_receipt",
    "load_accepted_risk_preliminary_pre_create_control",
    "load_accepted_risk_preliminary_result_read_permit",
    "load_accepted_risk_preliminary_submission_permit",
    "load_accepted_risk_preliminary_submission_plan",
    "load_accepted_risk_preliminary_terminal_status",
    "persist_accepted_risk_preliminary_submission_plan",
    "recover_accepted_risk_preliminary_launch_once",
    "read_accepted_risk_preliminary_result_once",
    "render_accepted_risk_preliminary_execution_authority_candidate",
    "render_accepted_risk_preliminary_result_read_authority_candidate",
    "require_accepted_risk_preliminary_aggregate_result",
    "require_accepted_risk_preliminary_launch_receipt",
    "require_accepted_risk_preliminary_result_read_permit",
    "require_accepted_risk_preliminary_submission_permit",
    "require_accepted_risk_preliminary_submission_plan",
    "require_accepted_risk_preliminary_terminal_status",
)
