"""One-attempt QC boundary for the outcome-free six-universe coverage probe.

No operation runs on import.  Production callers must use ``production_client``;
the functions accept an exact client so offline tests can replace its transport.
The claim is written before the first QC mutation.  An ambiguous failure leaves
that attempt spent and cannot be retried by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from research.quantconnect import API_BASE, QuantConnectClient

from . import accepted_risk_six_universe_coverage_qc_runtime as coverage
from . import accepted_risk_six_universe_coverage_qc_projection as source_builder
from .formal_qc_transport import MAX_RESPONSE_BYTES, _default_http_transport


class CoverageQcSubmissionError(ValueError):
    """An identity, control, or bounded QC response was refused."""


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]*\Z")
_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\.py\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DEFAULT_FILES = frozenset({"main.py", "research.ipynb"})
_TICKERS = ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
_MAX_FILE = source_builder.MAXIMUM_SOURCE_FILE_BYTES
_MAX_TOTAL_WITH_MARGIN = source_builder.MAXIMUM_TOTAL_SOURCE_BYTES


@dataclass(frozen=True)
class CoverageQcPlan:
    candidate_id: str
    attempt: int
    project_name: str
    backtest_name: str
    organization_id: str = field(repr=False)
    projection_sha256: str
    package_sha256: str
    activation_manifest_sha256: str
    # The QC SID resolution is computed inside the run. A prior reviewed
    # digest may be supplied, but the diagnostic does not invent one.
    symbol_resolution_sha256: str | None
    control_directory: Path


def production_client() -> QuantConnectClient:
    """Use the reviewed, redirect-refusing, 16 MiB bounded HTTP primitive."""
    return QuantConnectClient(transport=_bounded_transport)


def _bounded_transport(url, body, headers, timeout):
    status, raw = _default_http_transport(url, body, headers, timeout)
    if (
        type(status) is not int or not 200 <= status < 300
        or type(raw) is not bytes or len(raw) > MAX_RESPONSE_BYTES
    ):
        _fail("coverage QC response status or byte bound changed")
    return status, raw


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fail(message: str):
    raise CoverageQcSubmissionError(message)


def preview_plan(plan: CoverageQcPlan, projection: object) -> dict[str, object]:
    """Validate and display only frozen identities; no filesystem or QC I/O."""
    if type(plan) is not CoverageQcPlan:
        _fail("coverage plan type changed")
    if (
        type(plan.candidate_id) is not str
        or not _SAFE.fullmatch(plan.candidate_id)
        or len(plan.candidate_id) > 64
        or type(plan.attempt) is not int
        or not 1 <= plan.attempt <= 3
        or type(plan.project_name) is not str
        or not _SAFE.fullmatch(plan.project_name)
        or len(plan.project_name.encode("ascii")) > 100
        or type(plan.backtest_name) is not str
        or not _SAFE.fullmatch(plan.backtest_name)
        or len(plan.backtest_name.encode("ascii")) > 200
        or type(plan.organization_id) is not str
        or not _ORG.fullmatch(plan.organization_id)
        or not isinstance(plan.control_directory, Path)
        or not plan.control_directory.is_absolute()
        or any(
            type(value) is not str or not _HEX.fullmatch(value)
            for value in (
                plan.projection_sha256, plan.package_sha256,
                plan.activation_manifest_sha256,
            )
        )
        or (
            plan.symbol_resolution_sha256 is not None
            and (
                type(plan.symbol_resolution_sha256) is not str
                or not _HEX.fullmatch(plan.symbol_resolution_sha256)
            )
        )
    ):
        _fail("coverage plan identity is not frozen and bounded")
    profile = coverage.require_six_universe_coverage_profile()
    if type(projection) is not source_builder.SixUniverseCoverageQcProjection:
        _fail("coverage projection type changed")
    if (
        getattr(projection, "projection_sha256", None) != plan.projection_sha256
        or getattr(projection, "profile_id", None) != profile["profile_id"]
        or getattr(projection, "profile_sha256", None) != profile["profile_sha256"]
        or getattr(projection, "package_sha256", None) != plan.package_sha256
        or getattr(projection, "activation_manifest_sha256", None)
        != plan.activation_manifest_sha256
        or getattr(projection, "statistic_names", None)
        != coverage.expected_custom_summary_statistic_names()
    ):
        _fail("coverage projection or profile identity changed")
    files = getattr(projection, "source_files", None)
    if type(files) is not tuple or not files:
        _fail("coverage source inventory is absent")
    records = []
    for item in files:
        path = getattr(item, "project_path", None)
        source = getattr(item, "source_bytes", None)
        digest = getattr(item, "content_sha256", None)
        if (
            type(path) is not str or not _PATH.fullmatch(path)
            or ".." in Path(path).parts
            or type(source) is not bytes or not 0 < len(source) <= _MAX_FILE
            or type(digest) is not str
            or hashlib.sha256(source).hexdigest() != digest
        ):
            _fail("coverage projected file identity changed")
        try:
            source.decode("ascii")
        except UnicodeError:
            _fail("coverage projected source is not ASCII")
        records.append({"path": path, "sha256": digest, "bytes": len(source)})
    if (
        len({item["path"] for item in records}) != len(records)
        or "main.py" not in {item["path"] for item in records}
        or sum(item["bytes"] for item in records) > _MAX_TOTAL_WITH_MARGIN
        or getattr(projection, "total_source_byte_count", None)
        != sum(item["bytes"] for item in records)
    ):
        _fail("coverage projected source closure changed")
    record = projection.to_record()
    if (
        record.get("projection_sha256") != plan.projection_sha256
        or _sha({key: value for key, value in record.items()
                 if key not in {"projection_id", "projection_sha256"}})
        != plan.projection_sha256
    ):
        _fail("coverage projection self-authentication changed")
    return {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_name": plan.project_name, "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": records,
        "custom_statistic_names": list(coverage.expected_custom_summary_statistic_names()),
        "maximum_attempts": 3, "quantconnect_io_performed": False,
    }


def _client(api: QuantConnectClient) -> None:
    if (
        type(api) is not QuantConnectClient
        or api._base_url != API_BASE
        or api._transport is not _bounded_transport
    ):
        _fail("coverage client is not the bounded production transport")


def _post(api: QuantConnectClient, endpoint: str, payload: dict) -> dict:
    allowed = {
        "authenticate", "projects/read", "projects/create", "files/read",
        "files/delete", "files/create", "files/update", "compile/create",
        "compile/read", "backtests/create", "backtests/list", "backtests/read",
    }
    if endpoint not in allowed:
        _fail("coverage QC endpoint is not allowlisted")
    try:
        result = api.request(endpoint, payload)
    except Exception:
        raise CoverageQcSubmissionError("coverage QC " + endpoint + " failed") from None
    if type(result) is not dict or result.get("success") is not True:
        _fail("coverage QC " + endpoint + " response changed")
    return result


def _control_directory(plan: CoverageQcPlan) -> Path:
    path = plan.control_directory
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        _fail("coverage control directory is unavailable")
    info = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        _fail("coverage control directory is not private")
    return path


def _path(plan: CoverageQcPlan, suffix: str, attempt: int | None = None) -> Path:
    number = plan.attempt if attempt is None else attempt
    return _control_directory(plan) / (
        f"{plan.candidate_id}-A{number}-{suffix}.json"
    )


def _read_control(path: Path) -> dict:
    try:
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            _fail("coverage control file is not private")
        raw = path.read_bytes()
        if not 0 < len(raw) <= 64 * 1024:
            _fail("coverage control file exceeds bound")
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeError, ValueError):
        raise CoverageQcSubmissionError("coverage control file is unavailable") from None
    if type(value) is not dict or _canonical(value) != raw:
        _fail("coverage control file changed")
    return value


def _write_once(path: Path, value: dict) -> None:
    raw = _canonical(value)
    if len(raw) > 64 * 1024:
        _fail("coverage control record exceeds bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
    except OSError:
        raise CoverageQcSubmissionError("coverage one-use control was already spent") from None


def _claim_attempt(plan: CoverageQcPlan, preview: dict) -> None:
    for ordinal in range(1, 4):
        claim = _path(plan, "claim", ordinal)
        terminal = _path(plan, "terminal", ordinal)
        if ordinal < plan.attempt:
            if not claim.exists() or not terminal.exists():
                _fail("prior coverage attempt is unresolved")
            prior = _read_control(terminal)
            if prior.get("status") not in {"BuildError", "Runtime Error"}:
                _fail("prior coverage attempt did not fail terminally")
        elif claim.exists() or terminal.exists():
            _fail("coverage attempt already exists")
    _write_once(_path(plan, "claim"), {
        "candidate_id": plan.candidate_id,
        "attempt": plan.attempt,
        "project_name": plan.project_name,
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_sha256": preview["profile_sha256"],
    })


def _project(response: dict, plan: CoverageQcPlan) -> int:
    rows = response.get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        _fail("coverage project response changed")
    row = rows[0]
    project_id = row.get("projectId")
    if (
        type(project_id) is not int or project_id <= 0
        or row.get("name") != plan.project_name
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
    ):
        _fail("coverage project identity changed")
    return project_id


def prepare_and_launch_once(
    plan: CoverageQcPlan, projection: object, api: QuantConnectClient,
) -> dict[str, object]:
    """Create one fresh project, verify exact source, compile, and launch once."""
    preview = preview_plan(plan, projection)
    _client(api)
    if _path(plan, "claim").exists():
        _fail("coverage attempt already exists")
    _post(api, "authenticate", {})
    inventory = _post(api, "projects/read", {}).get("projects")
    if type(inventory) is not list or any(
        type(row) is not dict or row.get("name") == plan.project_name
        for row in inventory
    ):
        _fail("coverage project name is not fresh")
    _claim_attempt(plan, preview)
    project_id = _project(_post(api, "projects/create", {
        "name": plan.project_name, "language": "Py",
        "organizationId": plan.organization_id,
    }), plan)
    verified = _post(api, "projects/read", {"projectId": project_id})
    if _project(verified, plan) != project_id:
        _fail("coverage project readback changed")
    row = verified["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("coverage project is not private and idle")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in _DEFAULT_FILES
        for item in initial
    ):
        _fail("coverage new project has unexpected files")
    names = [item["name"] for item in initial]
    if len(set(names)) != len(names):
        _fail("coverage default file inventory changed")
    if "research.ipynb" in names:
        _post(api, "files/delete", {"projectId": project_id, "name": "research.ipynb"})
    for item in projection.source_files:
        endpoint = "files/update" if item.project_path == "main.py" and "main.py" in names else "files/create"
        _post(api, endpoint, {
            "projectId": project_id, "name": item.project_path,
            "content": item.source_bytes.decode("ascii"),
        })
    readback = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(readback) is not list or len(readback) != len(projection.source_files):
        _fail("coverage source readback inventory changed")
    observed = {}
    for item in readback:
        if type(item) is not dict or type(item.get("name")) is not str or type(item.get("content")) is not str:
            _fail("coverage source readback shape changed")
        if item["name"] in observed or item.get("projectId") != project_id:
            _fail("coverage source readback identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {item.project_path for item in projection.source_files}:
        _fail("coverage source readback paths changed")
    for item in projection.source_files:
        try:
            source = observed[item.project_path].encode("ascii")
        except UnicodeError:
            _fail("coverage source readback is not ASCII")
        if source != item.source_bytes or hashlib.sha256(source).hexdigest() != item.content_sha256:
            _fail("coverage source readback bytes changed")
    started = _post(api, "compile/create", {"projectId": project_id})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("coverage compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": project_id, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("coverage compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("coverage compile poll budget exhausted; attempt remains consumed")
    if state["state"] == "BuildError":
        _write_once(_path(plan, "terminal"), {
            "candidate_id": plan.candidate_id, "attempt": plan.attempt,
            "status": "BuildError", "project_id": project_id,
            "compile_id": compile_id,
        })
        _fail("coverage compile failed; attempt was consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": plan.backtest_name,
    }).get("backtest")
    if type(launched) is not dict:
        _fail("coverage backtest launch response changed")
    backtest_id = launched.get("backtestId")
    if (
        type(backtest_id) is not str or not _ID.fullmatch(backtest_id)
        or launched.get("projectId") != project_id
        or launched.get("name") != plan.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("coverage backtest launch identity changed")
    receipt = {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": project_id, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "projection_sha256": plan.projection_sha256,
        "profile_id": preview["profile_id"],
        "profile_sha256": preview["profile_sha256"],
    }
    _write_once(_path(plan, "launch"), receipt)
    return receipt


def poll_status_once(plan: CoverageQcPlan, launch: dict, api: QuantConnectClient) -> str:
    """Inspect only exact backtest identity and status; never statistics."""
    _client(api)
    if _read_control(_path(plan, "launch")) != launch:
        _fail("coverage launch receipt changed")
    terminal_path = _path(plan, "terminal")
    if terminal_path.exists():
        return _read_control(terminal_path)["status"]
    result = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = result.get("backtests")
    if type(rows) is not list or result.get("count", len(rows)) != len(rows):
        _fail("coverage status inventory changed")
    matches = [item for item in rows if type(item) is dict and item.get("backtestId") == launch["backtest_id"]]
    if len(matches) != 1:
        _fail("coverage exact backtest status is absent")
    item = matches[0]
    status = item.get("status")
    if (
        item.get("name") != launch["backtest_name"]
        or ("projectId" in item and item["projectId"] != launch["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("coverage backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write_once(terminal_path, {
            "candidate_id": plan.candidate_id, "attempt": plan.attempt,
            "status": status, "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


def _strict_statistic(value: object) -> dict:
    if type(value) is not str or not value.isascii():
        _fail("coverage custom statistic is not ASCII")
    raw = value.encode("ascii")
    if not 0 < len(raw) <= coverage.MAXIMUM_STATISTIC_BYTES:
        _fail("coverage custom statistic exceeded its byte bound")
    try:
        record = json.loads(raw.decode("ascii"), parse_constant=lambda _: None)
    except ValueError:
        raise CoverageQcSubmissionError("coverage custom statistic is not JSON") from None
    if type(record) is not dict or _canonical(record) != raw:
        _fail("coverage custom statistic is not canonical JSON")
    return record


def _checked_counts(value: object, *, annual: bool = False) -> None:
    """Keep only the runtime's fixed aggregate fields, never a row or SID."""
    template = coverage._empty_counts()
    expected = set(template) | ({"year"} if annual else set())
    if type(value) is not dict or set(value) != expected:
        _fail("coverage count field inventory changed")
    if annual and (type(value["year"]) is not int or value["year"] not in coverage.YEARS):
        _fail("coverage year identity changed")
    for name, example in template.items():
        observed = value[name]
        if type(example) is int:
            if type(observed) is not int or not 0 <= observed <= coverage.MAXIMUM_TOTAL_SOURCE_ROWS:
                _fail("coverage count value changed")
        elif type(example) is dict:
            if type(observed) is not dict or set(observed) != set(example) or any(
                type(number) is not int or not 0 <= number <= coverage.EXPECTED_DECISION_COUNT
                for number in observed.values()
            ):
                _fail("coverage histogram changed")
        else:
            if type(observed) is not str or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", observed) is None:
                _fail("coverage aggregate weight changed")


def read_counts_once(plan: CoverageQcPlan, launch: dict, api: QuantConnectClient) -> dict:
    """Spend one read, then retain only seven hash-bound custom count objects."""
    _client(api)
    if _read_control(_path(plan, "launch")) != launch:
        _fail("coverage launch receipt changed")
    terminal = _read_control(_path(plan, "terminal"))
    if terminal.get("status") != "Completed." or terminal.get("backtest_id") != launch["backtest_id"]:
        _fail("coverage run did not complete exactly")
    _write_once(_path(plan, "result-read-claim"), {
        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    })
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"], "backtestId": launch["backtest_id"],
    })
    return _parse_counts_response(response, plan, launch)


def _parse_counts_response(response: dict, plan: CoverageQcPlan, launch: dict) -> dict:
    """Retain only the seven schema- and digest-bound coverage statistics."""
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != launch["backtest_name"]
        or backtest.get("status") != "Completed."
    ):
        _fail("coverage result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict:
        _fail("coverage summary statistic mapping is absent")
    expected = coverage.expected_custom_summary_statistic_names()
    selected = tuple(sorted(key for key in statistics if type(key) is str and key.startswith("ARV2_SIX_COVERAGE_")))
    if selected != expected:
        _fail("coverage custom statistic inventory changed")
    parsed = {name: _strict_statistic(statistics[name]) for name in expected}
    meta = parsed[coverage.META_STATISTIC_NAME]
    if (
        set(meta) != {
            "schema", "profile_id", "profile_sha256", "package_id",
            "package_sha256", "activation_manifest_sha256",
            "symbol_resolution_id", "symbol_resolution_sha256",
            "decision_count", "sleeve_decision_count",
            "callback_source_row_count", "coverage_path_sha256",
            "sleeve_sha256s", "aggregate_sha256",
            "raw_rows_or_identifiers_emitted", "price_or_return_access",
            "orders", "backtest_only",
        }
        or
        meta.get("schema") != coverage.META_SCHEMA
        or meta.get("profile_id") != launch["profile_id"]
        or meta.get("profile_sha256") != launch["profile_sha256"]
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("activation_manifest_sha256") != plan.activation_manifest_sha256
        or (
            plan.symbol_resolution_sha256 is not None
            and meta.get("symbol_resolution_sha256")
            != plan.symbol_resolution_sha256
        )
        or type(meta.get("symbol_resolution_sha256")) is not str
        or _HEX.fullmatch(meta["symbol_resolution_sha256"]) is None
        or meta.get("decision_count") != coverage.EXPECTED_DECISION_COUNT
        or meta.get("sleeve_decision_count") != coverage.EXPECTED_SLEEVE_DECISION_COUNT
        or meta.get("raw_rows_or_identifiers_emitted") is not False
        or meta.get("price_or_return_access") is not False
        or meta.get("orders") is not False
        or meta.get("backtest_only") is not True
        or type(meta.get("package_id")) is not str
        or type(meta.get("symbol_resolution_id")) is not str
        or type(meta.get("callback_source_row_count")) is not int
        or not 0 <= meta["callback_source_row_count"] <= coverage.MAXIMUM_TOTAL_SOURCE_ROWS
        or type(meta.get("coverage_path_sha256")) is not str
        or _HEX.fullmatch(meta["coverage_path_sha256"]) is None
    ):
        _fail("coverage result metadata changed")
    sleeves = [parsed[coverage.SLEEVE_STATISTIC_PREFIX + ticker] for ticker in _TICKERS]
    digests = meta.get("sleeve_sha256s")
    if type(digests) is not dict or set(digests) != set(_TICKERS):
        _fail("coverage sleeve digest inventory changed")
    for ticker, sleeve in zip(_TICKERS, sleeves):
        if (
            sleeve.get("schema") != coverage.SLEEVE_SCHEMA
            or sleeve.get("universe_id") != ticker
            or digests[ticker] != _sha(sleeve)
            or set(sleeve) != {"schema", "universe_id", "totals", "years"}
        ):
            _fail("coverage sleeve identity or digest changed")
        _checked_counts(sleeve["totals"])
        years = sleeve["years"]
        if type(years) is not list or len(years) != len(coverage.YEARS):
            _fail("coverage annual count inventory changed")
        for year, row in zip(coverage.YEARS, years):
            _checked_counts(row, annual=True)
            if row["year"] != year:
                _fail("coverage annual count order changed")
        if (
            sleeve["totals"]["decision_count"] != coverage.EXPECTED_DECISION_COUNT
            or sum(row["decision_count"] for row in years) != coverage.EXPECTED_DECISION_COUNT
        ):
            _fail("coverage decision census changed")
    if meta.get("aggregate_sha256") != _sha(sleeves):
        _fail("coverage aggregate digest changed")
    return {"meta": meta, "sleeves": dict(zip(_TICKERS, sleeves))}


def read_imported_counts_once(
    plan: CoverageQcPlan, projection: source_builder.SixUniverseCoverageQcProjection,
    *, project_id: int, backtest_id: str, snapshot_id: int,
    api: QuantConnectClient,
) -> dict:
    """Read a Mia-completed run once after attesting its current project source.

    QC's file API does not expose historical snapshot contents. The exact
    current source must match the frozen projection and every file must have
    been last modified before this run was created. This is a bounded timing
    attestation, not a claim of historical snapshot byte access.
    """
    preview = preview_plan(plan, projection)
    _client(api)
    if (
        type(project_id) is not int or project_id <= 0
        or type(backtest_id) is not str or not _ID.fullmatch(backtest_id)
        or type(snapshot_id) is not int or snapshot_id <= 0
    ):
        _fail("coverage imported run identity changed")
    project = _post(api, "projects/read", {"projectId": project_id})
    if _project(project, plan) != project_id:
        _fail("coverage imported project identity changed")
    owner = project["projects"][0]
    collaborators = owner.get("collaborators")
    if (
        owner.get("owner") is not True
        or type(collaborators) is not list or len(collaborators) > 2
        or any(type(item) is not dict for item in collaborators)
        or sum(item.get("owner") is True for item in collaborators) != 1
    ):
        _fail("coverage imported project collaborator inventory changed")
    readback = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(readback) is not list or len(readback) != len(projection.source_files):
        _fail("coverage imported source inventory changed")
    observed = {}
    modified = []
    for item in readback:
        if (
            type(item) is not dict or item.get("projectId") != project_id
            or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("coverage imported source identity changed")
        observed[item["name"]] = item["content"]
        try:
            stamp = datetime.fromisoformat(item["modified"])
        except (KeyError, TypeError, ValueError):
            _fail("coverage imported source modification time changed")
        if stamp.tzinfo is not None:
            _fail("coverage imported source time basis changed")
        modified.append(stamp)
    if set(observed) != {item.project_path for item in projection.source_files}:
        _fail("coverage imported source paths changed")
    for item in projection.source_files:
        if observed[item.project_path] != item.source_bytes.decode("ascii"):
            _fail("coverage imported source bytes changed")
    listing = _post(api, "backtests/list", {
        "projectId": project_id, "includeStatistics": False,
    })
    rows = listing.get("backtests")
    if type(rows) is not list or listing.get("count", len(rows)) != len(rows):
        _fail("coverage imported run inventory changed")
    matches = [row for row in rows if type(row) is dict and row.get("backtestId") == backtest_id]
    if len(matches) != 1:
        _fail("coverage imported run is absent")
    run = matches[0]
    try:
        created = datetime.fromisoformat(run["created"])
    except (KeyError, TypeError, ValueError):
        _fail("coverage imported run creation time changed")
    if (
        created.tzinfo is not None
        or max(modified) > created
        or run.get("projectId") != project_id
        or run.get("name") != plan.backtest_name
        or run.get("status") != "Completed."
        or run.get("snapshotId") != snapshot_id
    ):
        _fail("coverage imported run did not match frozen source and terminal identity")
    _write_once(_path(plan, "import-result-read-claim"), {
        "candidate_id": plan.candidate_id, "project_id": project_id,
        "backtest_id": backtest_id, "snapshot_id": snapshot_id,
        "projection_sha256": preview["projection_sha256"],
    })
    response = _post(api, "backtests/read", {
        "projectId": project_id, "backtestId": backtest_id,
    })
    backtest = response.get("backtest")
    if type(backtest) is not dict or backtest.get("snapshotId") != snapshot_id:
        _fail("coverage imported result snapshot changed")
    launch = {
        "project_id": project_id, "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "profile_id": preview["profile_id"],
        "profile_sha256": preview["profile_sha256"],
    }
    return _parse_counts_response(response, plan, launch)


__all__ = (
    "CoverageQcPlan", "CoverageQcSubmissionError", "preview_plan",
    "prepare_and_launch_once", "poll_status_once", "production_client",
    "read_counts_once", "read_imported_counts_once",
)
