"""Offline-first, input-only R247 QC submission; no action occurs on import.

The prospective A3 runtime correction reuses A2's generated main and the
same private project. A failed attempt consumes its claim; no A4 is permitted.
The sole result read retains one bounded metadata statistic, not QC data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import fresh_six_universe_snapshot as snapshot
from . import six_universe_coverage_submission as boundary


class FreshSnapshotSubmissionError(ValueError):
    """A frozen identity, local control, or bounded QC response was refused."""


CANDIDATE_ID = "R247"
DECISION_SESSION = "2026-09-25"
PROJECT_NAME = "ARV2 R247 FRESH SIX INPUT 20260925"
BACKTEST_NAME = "ARV2 R247A1 fresh six input 20260925"
BACKTEST_NAME_A2 = "ARV2 R247A2 fresh six input init error disclosure 20260925"
BACKTEST_NAME_A3 = "ARV2 R247A3 fresh six input runtime correction 20260925"
PROJECT_ID_A3 = 37097547
META_NAME = "ARV2_FRESH_SIX_INPUT_META"
WAIVER_SCHEMA = "arv2-r247-fresh-six-input-exact-owner-waiver-v1"
WAIVER_SCHEMA_A2 = "arv2-r247a2-fresh-six-input-exact-owner-waiver-v1"
WAIVER_SCHEMA_A3 = "arv2-r247a3-fresh-six-input-exact-owner-waiver-v1"
# Derived candidate binding under the owner's standing exploratory waiver
# recorded in lane sections 191/192/195; not a new owner statement.
WAIVER_ID = "ARV2-OWNER-STANDING-EXPLORATORY-R247A1-INPUT-ONLY-SIGNATURE-WAIVER"
WAIVER_ID_A2 = "ARV2-OWNER-STANDING-EXPLORATORY-R247A2-INPUT-ONLY-SIGNATURE-WAIVER"
WAIVER_ID_A3 = "ARV2-OWNER-STANDING-EXPLORATORY-R247A3-INPUT-ONLY-SIGNATURE-WAIVER"
RUNTIME_SHA256 = "6c386957b25b83d6a5f6333cfa699ae07e0808b965a5a9184059becd992e529f"
RUNTIME_SHA256_A3 = "39b519dccde32aa2a86499873015adcd0a377b8ca0c69905f9609e6411a2f0c9"
MAIN_SHA256 = "6138e86c6589e88f26f1cfddb646d46d692d8e412fe6b26ef09b2df4fa1f955e"
MAIN_SHA256_A2 = "9227144284e54ba3894ee86a7fea3e3d1f06a8892d5a7eebf3068b5eac123830"
SOURCE_MANIFEST_SHA256 = "3954de79a3398e900a78e6c2f0330ff9cdda370ade3570e41dbe50380684b381"
SOURCE_MANIFEST_SHA256_A2 = "123c17148c6850cf432dbf64534de7c3f040324b80639ada369567867b0c7f9d"
SOURCE_MANIFEST_SHA256_A3 = "104a7afb8298a52537ef42a3c29eb2d86f8565807a5e6affde73816450877cce"
MAX_SOURCE_FILE_BYTES = 64_000
MAX_META_BYTES = 2_048
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DEFAULT_FILES = frozenset({"main.py", "research.ipynb"})
_POST = boundary._post
_CLIENT = boundary._client
_READ_CONTROL = boundary._read_control
_WRITE_ONCE = boundary._write_once
_CONTROL_DIRECTORY = boundary._control_directory


@dataclass(frozen=True)
class SnapshotQcPlan:
    organization_id: str
    control_directory: Path
    attempt: int = 1


def _fail(message: str):
    raise FreshSnapshotSubmissionError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _main_for_attempt(attempt: int) -> bytes:
    main = snapshot.main_source(DECISION_SESSION)
    if attempt in {2, 3}:
        old = "    def on_end_of_algorithm(self):\n        self._snapshot.require_persisted()\n"
        new = (
            "    def on_end_of_algorithm(self):\n"
            "        if self.time.date().isoformat() >= '2026-09-25':\n"
            "            self._snapshot.require_persisted()\n"
        )
        if main.count(old) != 1:
            _fail("R247 A2/A3 one-line on_end source anchor changed")
        main = main.replace(old, new)
    return main.encode("ascii")


def _runtime_for_attempt(attempt: int) -> bytes:
    """Recover the pinned A1/A2 upload from A3's two exact source edits."""
    source = Path(snapshot.__file__).read_bytes()
    if _digest(source) != RUNTIME_SHA256_A3:
        _fail("R247 A3 runtime source bytes changed")
    if attempt == 3:
        return source
    callback_new = (
        b"    # QC's Python bridge may supply a datetime subtype. Other completed lane\n"
        b"    # runtimes accept that shape; exact-type equality rejected it at initialize.\n"
        b"    if not isinstance(value, datetime):\n"
    )
    callback_old = b"    if type(value) is not datetime:\n"
    end_time_new = b"        if not isinstance(value, datetime):\n"
    end_time_old = b"        if type(value) is not datetime:\n"
    if source.count(callback_new) != 1 or source.count(end_time_new) != 1:
        _fail("R247 A3 runtime correction anchors changed")
    prior = source.replace(callback_new, callback_old, 1).replace(
        end_time_new, end_time_old, 1,
    )
    if _digest(prior) != RUNTIME_SHA256:
        _fail("R247 A1/A2 runtime reconstruction changed")
    return prior


def _files(attempt: int = 1) -> tuple[tuple[str, bytes], ...]:
    """Read the exact committed runtime, then authenticate generated main."""
    if attempt not in {1, 2, 3}:
        _fail("R247 attempt is not implemented")
    try:
        source = _runtime_for_attempt(attempt)
        main = _main_for_attempt(attempt)
    except (OSError, UnicodeError, ValueError) as exc:
        raise FreshSnapshotSubmissionError("R247 source is unavailable") from exc
    files = tuple(sorted((
        ("fresh_six_universe_snapshot.py", source), ("main.py", main),
    )))
    if (
        _digest(source) != (RUNTIME_SHA256_A3 if attempt == 3 else RUNTIME_SHA256)
        or _digest(main) != (MAIN_SHA256 if attempt == 1 else MAIN_SHA256_A2)
        or any(not 0 < len(raw) <= MAX_SOURCE_FILE_BYTES or not raw.isascii()
               for _, raw in files)
    ):
        _fail("R247 frozen source bytes changed")
    return files


def preview_plan(plan: SnapshotQcPlan) -> dict[str, object]:
    """Pure offline preview; no credentials, control write, or QC request."""
    if (
        type(plan) is not SnapshotQcPlan
        or type(plan.organization_id) is not str
        or _ORG.fullmatch(plan.organization_id) is None
        or type(plan.control_directory) is not type(Path())
        or not plan.control_directory.is_absolute()
        or ".." in plan.control_directory.parts
        or type(plan.attempt) is not int or plan.attempt not in {1, 2, 3}
    ):
        _fail("R247 permits only frozen A1/A2/A3 in an absolute control directory")
    files = _files(plan.attempt)
    inventory = [
        {"path": path, "sha256": _digest(raw), "bytes": len(raw)}
        for path, raw in files
    ]
    manifest_sha = _digest(_canonical(inventory))
    expected_manifest = {
        1: SOURCE_MANIFEST_SHA256,
        2: SOURCE_MANIFEST_SHA256_A2,
        3: SOURCE_MANIFEST_SHA256_A3,
    }[plan.attempt]
    if manifest_sha != expected_manifest:
        _fail("R247 two-file source manifest changed")
    return {
        "candidate_id": CANDIDATE_ID, "attempt": plan.attempt,
        "decision_session": DECISION_SESSION,
        "project_name": PROJECT_NAME,
        "backtest_name": {
            1: BACKTEST_NAME, 2: BACKTEST_NAME_A2, 3: BACKTEST_NAME_A3,
        }[plan.attempt],
        "source_manifest_sha256": manifest_sha, "source_files": inventory,
        "custom_statistic_name": META_NAME,
        "maximum_attempts_same_project": 3,
        "implemented_attempts": list(range(1, plan.attempt + 1)),
        "quantconnect_io_performed": False,
    }


def render_owner_waiver_payload(plan: SnapshotQcPlan) -> bytes:
    """Bind the standing exploratory waiver to only this exact input probe."""
    preview = preview_plan(plan)
    is_a1 = plan.attempt == 1
    body = {
        "schema": {
            1: WAIVER_SCHEMA, 2: WAIVER_SCHEMA_A2, 3: WAIVER_SCHEMA_A3,
        }[plan.attempt],
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": {
            1: WAIVER_ID, 2: WAIVER_ID_A2, 3: WAIVER_ID_A3,
        }[plan.attempt],
        "action": "one_private_input_only_snapshot_backtest_launch",
        "candidate_id": CANDIDATE_ID, "attempt": plan.attempt,
        "organization_id_sha256": _digest(plan.organization_id.encode("ascii")),
        "control_directory": str(plan.control_directory),
        "decision_session": DECISION_SESSION,
        "project_name": PROJECT_NAME, "backtest_name": preview["backtest_name"],
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "source_files": preview["source_files"],
        "custom_statistic_name": META_NAME,
        "mutating_endpoint_budget": {
            "projects/create": 1 if is_a1 else 0,
            "files/delete": 1 if is_a1 else 0,
            "files/update": 1, "files/create": 1 if is_a1 else 0,
            "compile/create": 1, "backtests/create": 1,
        },
        "maximum_attempts_same_project": 3,
        "maximum_backtest_submissions_this_waiver": 1,
        "bounded_meta_result_read_authorized": True,
        "object_store_download_authorized": False,
        "prices_returns_orders_authorized": False,
        "paper_live_broker_trading_authorized": False,
    }
    if plan.attempt == 2:
        predecessor, _ = _require_failed_a1(plan)
        body.update({
            "predecessor_project_id": predecessor["project_id"],
            "predecessor_backtest_id": predecessor["backtest_id"],
            "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        })
    elif plan.attempt == 3:
        predecessor, first = _require_failed_a2(plan)
        body.update({
            "predecessor_project_id": PROJECT_ID_A3,
            "predecessor_backtest_id": predecessor["backtest_id"],
            "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256_A2,
            "first_backtest_id": first["backtest_id"],
            "first_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        })
    return _canonical(body)


def _launch_authority(
    plan: SnapshotQcPlan, *, owner_waiver_id: str | None,
) -> dict[str, str]:
    expected_id = {
        1: WAIVER_ID, 2: WAIVER_ID_A2, 3: WAIVER_ID_A3,
    }[plan.attempt]
    if type(owner_waiver_id) is not str or owner_waiver_id != expected_id:
        _fail("R247 standing owner waiver does not cover this candidate")
    return {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": {
            1: WAIVER_SCHEMA, 2: WAIVER_SCHEMA_A2, 3: WAIVER_SCHEMA_A3,
        }[plan.attempt],
        "owner_launch_waiver_id": expected_id,
        "owner_waived_payload_sha256": _digest(render_owner_waiver_payload(plan)),
    }


def production_client():
    return boundary.production_client()


def _client(api):
    try:
        _CLIENT(api)
    except boundary.CoverageQcSubmissionError:
        raise FreshSnapshotSubmissionError("R247 bounded QC client is unavailable") from None


def _post(api, endpoint: str, payload: dict) -> dict:
    try:
        return _POST(api, endpoint, payload)
    except boundary.CoverageQcSubmissionError:
        raise FreshSnapshotSubmissionError("R247 QC " + endpoint + " failed") from None


def _path(plan: SnapshotQcPlan, suffix: str) -> Path:
    try:
        return _CONTROL_DIRECTORY(plan) / f"{CANDIDATE_ID}-A{plan.attempt}-{suffix}.json"
    except boundary.CoverageQcSubmissionError:
        raise FreshSnapshotSubmissionError("R247 private control directory is unavailable") from None


def _read(path: Path) -> dict:
    try:
        return _READ_CONTROL(path)
    except boundary.CoverageQcSubmissionError:
        raise FreshSnapshotSubmissionError("R247 private control is unavailable") from None


def _write(path: Path, value: dict) -> None:
    try:
        _WRITE_ONCE(path, value)
    except boundary.CoverageQcSubmissionError:
        raise FreshSnapshotSubmissionError("R247 one-use control was already spent") from None


def _project(response: dict, plan: SnapshotQcPlan) -> int:
    rows = response.get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        _fail("R247 project response changed")
    row = rows[0]
    project_id = row.get("projectId")
    if (
        type(project_id) is not int or project_id <= 0
        or row.get("name") != PROJECT_NAME
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
    ):
        _fail("R247 project identity changed")
    return project_id


def _require_source_readback(api, project_id: int, files: tuple[tuple[str, bytes], ...]) -> None:
    readback = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(readback) is not list or len(readback) != len(files):
        _fail("R247 two-file readback inventory changed")
    observed = {}
    for item in readback:
        if (
            type(item) is not dict or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item.get("projectId") != project_id
            or item["name"] in observed
        ):
            _fail("R247 source readback identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {path for path, _ in files}:
        _fail("R247 source readback paths changed")
    for path, raw in files:
        try:
            rendered = observed[path].encode("ascii")
        except UnicodeError:
            _fail("R247 source readback is not ASCII")
        if rendered != raw or _digest(rendered) != _digest(raw):
            _fail("R247 source readback bytes changed")


def _compile_and_launch(plan: SnapshotQcPlan, api, project_id: int) -> tuple[str, str]:
    name = {
        1: BACKTEST_NAME, 2: BACKTEST_NAME_A2, 3: BACKTEST_NAME_A3,
    }[plan.attempt]
    started = _post(api, "compile/create", {"projectId": project_id})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or _ID.fullmatch(compile_id) is None:
        _fail("R247 compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": project_id, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("R247 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("R247 compile poll budget exhausted; attempt is consumed")
    if state["state"] == "BuildError":
        _write(_path(plan, "terminal"), {
            "candidate_id": CANDIDATE_ID, "attempt": plan.attempt,
            "status": "BuildError", "project_id": project_id,
            "compile_id": compile_id,
        })
        _fail("R247 compile failed; attempt is consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": name,
    }).get("backtest")
    if type(launched) is not dict:
        _fail("R247 launch response changed")
    backtest_id = launched.get("backtestId")
    if (
        type(backtest_id) is not str or _ID.fullmatch(backtest_id) is None
        or launched.get("projectId") != project_id
        or launched.get("name") != name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("R247 backtest launch identity changed")
    return compile_id, backtest_id


def prepare_and_launch_once(
    plan: SnapshotQcPlan, api, *, owner_waiver_id: str | None = None,
) -> dict[str, object]:
    """One exact-waived attempt with a one-use claim and exact source."""
    preview = preview_plan(plan)
    permit = _launch_authority(plan, owner_waiver_id=owner_waiver_id)
    if plan.attempt == 2:
        return _prepare_and_launch_a2_once(plan, api, preview, permit)
    if plan.attempt == 3:
        return _prepare_and_launch_a3_once(plan, api, preview, permit)
    files = _files()  # Immutable bytes carried through upload/readback.
    _client(api)
    if _path(plan, "claim").exists():
        _fail("R247 A1 was already claimed")
    _post(api, "authenticate", {})
    inventory = _post(api, "projects/read", {}).get("projects")
    if type(inventory) is not list or any(
        type(row) is not dict or row.get("name") == PROJECT_NAME
        for row in inventory
    ):
        _fail("R247 project name is not fresh")
    _write(_path(plan, "claim"), {
        **permit, "candidate_id": CANDIDATE_ID, "attempt": 1,
        "decision_session": DECISION_SESSION, "project_name": PROJECT_NAME,
        "source_manifest_sha256": preview["source_manifest_sha256"],
    })
    project_id = _project(_post(api, "projects/create", {
        "name": PROJECT_NAME, "language": "Py",
        "organizationId": plan.organization_id,
    }), plan)
    verified = _post(api, "projects/read", {"projectId": project_id})
    if _project(verified, plan) != project_id:
        _fail("R247 project readback changed")
    row = verified["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True
               for item in collaborators)
    ):
        _fail("R247 project is not private and idle")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in _DEFAULT_FILES
        for item in initial
    ):
        _fail("R247 fresh-project file inventory changed")
    names = [item["name"] for item in initial]
    if len(set(names)) != len(names) or "main.py" not in names:
        _fail("R247 fresh default main file is absent or duplicated")
    if "research.ipynb" in names:
        _post(api, "files/delete", {
            "projectId": project_id, "name": "research.ipynb",
        })
    for path, raw in files:
        endpoint = "files/update" if path == "main.py" else "files/create"
        _post(api, endpoint, {
            "projectId": project_id, "name": path,
            "content": raw.decode("ascii"),
        })
    _require_source_readback(api, project_id, files)
    compile_id, backtest_id = _compile_and_launch(plan, api, project_id)
    receipt = {
        **permit, "candidate_id": CANDIDATE_ID, "attempt": 1,
        "decision_session": DECISION_SESSION,
        "project_id": project_id, "project_name": PROJECT_NAME,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "backtest_name": BACKTEST_NAME,
        "source_manifest_sha256": preview["source_manifest_sha256"],
    }
    _write(_path(plan, "launch"), receipt)
    return receipt


def _prepare_and_launch_a2_once(
    plan: SnapshotQcPlan, api, preview: dict, permit: dict[str, str],
) -> dict[str, object]:
    """Reuse A1's exact private project; change only generated main.py."""
    predecessor, _ = _require_failed_a1(plan)
    project_id = predecessor["project_id"]
    a1_files = _files(1)
    a2_files = _files(2)
    _client(api)
    if _path(plan, "claim").exists() or _path(plan, "launch").exists():
        _fail("R247 A2 was already claimed")
    _post(api, "authenticate", {})
    verified = _post(api, "projects/read", {"projectId": project_id})
    if _project(verified, plan) != project_id:
        _fail("R247 A2 predecessor project changed")
    row = verified["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True
               for item in collaborators)
    ):
        _fail("R247 A2 predecessor project is not private and idle")
    _require_source_readback(api, project_id, a1_files)
    status = _post(api, "backtests/list", {
        "projectId": project_id, "includeStatistics": False,
    })
    rows = status.get("backtests")
    if type(rows) is not list or len(rows) != 1 or status.get("count", len(rows)) != len(rows):
        _fail("R247 A1 status inventory changed")
    matches = [item for item in rows if type(item) is dict
               and item.get("backtestId") == predecessor["backtest_id"]]
    if len(matches) != 1 or (
        matches[0].get("projectId", project_id) != project_id
        or matches[0].get("name") != BACKTEST_NAME
        or matches[0].get("status") != "Runtime Error"
    ):
        _fail("R247 A1 terminal status changed")
    _write(_path(plan, "claim"), {
        **permit, "candidate_id": CANDIDATE_ID, "attempt": 2,
        "decision_session": DECISION_SESSION, "project_name": PROJECT_NAME,
        "project_id": project_id,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "predecessor_backtest_id": predecessor["backtest_id"],
        "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
    })
    a2_main = next(raw for path, raw in a2_files if path == "main.py")
    _post(api, "files/update", {
        "projectId": project_id, "name": "main.py",
        "content": a2_main.decode("ascii"),
    })
    _require_source_readback(api, project_id, a2_files)
    compile_id, backtest_id = _compile_and_launch(plan, api, project_id)
    receipt = {
        **permit, "candidate_id": CANDIDATE_ID, "attempt": 2,
        "decision_session": DECISION_SESSION,
        "project_id": project_id, "project_name": PROJECT_NAME,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "backtest_name": BACKTEST_NAME_A2,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "predecessor_backtest_id": predecessor["backtest_id"],
        "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
    }
    _write(_path(plan, "launch"), receipt)
    return receipt


def _prepare_and_launch_a3_once(
    plan: SnapshotQcPlan, api, preview: dict, permit: dict[str, str],
) -> dict[str, object]:
    """Reuse A2's failed project; update only the prospectively fixed runtime."""
    predecessor, first = _require_failed_a2(plan)
    project_id = PROJECT_ID_A3
    a2_files = _files(2)
    a3_files = _files(3)
    _client(api)
    if _path(plan, "claim").exists() or _path(plan, "launch").exists():
        _fail("R247 A3 was already claimed")
    _post(api, "authenticate", {})
    verified = _post(api, "projects/read", {"projectId": project_id})
    if _project(verified, plan) != project_id:
        _fail("R247 A3 predecessor project changed")
    row = verified["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True
               for item in collaborators)
    ):
        _fail("R247 A3 predecessor project is not private and idle")
    _require_source_readback(api, project_id, a2_files)
    status = _post(api, "backtests/list", {
        "projectId": project_id, "includeStatistics": False,
    })
    rows = status.get("backtests")
    if (
        type(rows) is not list or len(rows) != 2
        or status.get("count", len(rows)) != len(rows)
    ):
        _fail("R247 A3 predecessor run inventory changed")
    expected = {
        first["backtest_id"]: BACKTEST_NAME,
        predecessor["backtest_id"]: BACKTEST_NAME_A2,
    }
    if (
        len(expected) != 2
        or any(
            type(item) is not dict
            or item.get("backtestId") not in expected
            or item.get("projectId") != project_id
            or item.get("name") != expected[item["backtestId"]]
            or item.get("status") != "Runtime Error"
            for item in rows
        )
        or {item["backtestId"] for item in rows} != set(expected)
    ):
        _fail("R247 A3 predecessor run identity or terminal status changed")
    bindings = {
        "predecessor_backtest_id": predecessor["backtest_id"],
        "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256_A2,
        "first_backtest_id": first["backtest_id"],
        "first_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
    }
    _write(_path(plan, "claim"), {
        **permit, "candidate_id": CANDIDATE_ID, "attempt": 3,
        "decision_session": DECISION_SESSION, "project_name": PROJECT_NAME,
        "project_id": project_id,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        **bindings,
    })
    runtime = next(raw for path, raw in a3_files
                   if path == "fresh_six_universe_snapshot.py")
    _post(api, "files/update", {
        "projectId": project_id, "name": "fresh_six_universe_snapshot.py",
        "content": runtime.decode("ascii"),
    })
    _require_source_readback(api, project_id, a3_files)
    compile_id, backtest_id = _compile_and_launch(plan, api, project_id)
    receipt = {
        **permit, "candidate_id": CANDIDATE_ID, "attempt": 3,
        "decision_session": DECISION_SESSION,
        "project_id": project_id, "project_name": PROJECT_NAME,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "backtest_name": BACKTEST_NAME_A3,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        **bindings,
    }
    _write(_path(plan, "launch"), receipt)
    return receipt


def _launch(plan: SnapshotQcPlan, launch: dict) -> None:
    preview = preview_plan(plan)
    claim = _read(_path(plan, "claim"))
    if _read(_path(plan, "launch")) != launch or (
        launch.get("candidate_id") != CANDIDATE_ID
        or launch.get("attempt") != plan.attempt
        or launch.get("decision_session") != DECISION_SESSION
        or launch.get("project_name") != PROJECT_NAME
        or launch.get("backtest_name") != preview["backtest_name"]
        or launch.get("source_manifest_sha256") != preview["source_manifest_sha256"]
        or type(launch.get("project_id")) is not int
        or type(launch.get("backtest_id")) is not str
        or _ID.fullmatch(launch["backtest_id"]) is None
    ):
        _fail("R247 launch receipt changed")
    expected = _launch_authority(
        plan, owner_waiver_id={
            1: WAIVER_ID, 2: WAIVER_ID_A2, 3: WAIVER_ID_A3,
        }[plan.attempt],
    )
    if any(launch.get(key) != value for key, value in expected.items()):
        _fail("R247 launch waiver receipt changed")
    if (
        claim.get("candidate_id") != CANDIDATE_ID
        or claim.get("attempt") != plan.attempt
        or claim.get("decision_session") != DECISION_SESSION
        or claim.get("project_name") != PROJECT_NAME
        or claim.get("source_manifest_sha256") != preview["source_manifest_sha256"]
        or any(claim.get(key) != value for key, value in expected.items())
    ):
        _fail("R247 launch and claim authority differ")
    if plan.attempt == 2:
        predecessor, _ = _require_failed_a1(plan)
        if any(
            record.get(key) != value
            for record in (claim, launch)
            for key, value in {
                "project_id": predecessor["project_id"],
                "predecessor_backtest_id": predecessor["backtest_id"],
                "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            }.items()
        ):
            _fail("R247 A2 predecessor binding changed")
    if plan.attempt == 3:
        predecessor, first = _require_failed_a2(plan)
        bindings = {
            "project_id": PROJECT_ID_A3,
            "predecessor_backtest_id": predecessor["backtest_id"],
            "predecessor_source_manifest_sha256": SOURCE_MANIFEST_SHA256_A2,
            "first_backtest_id": first["backtest_id"],
            "first_source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        }
        if any(
            record.get(key) != value
            for record in (claim, launch)
            for key, value in bindings.items()
        ):
            _fail("R247 A3 predecessor binding changed")


def _require_failed_a1(plan: SnapshotQcPlan) -> tuple[dict, dict]:
    prior_plan = SnapshotQcPlan(plan.organization_id, plan.control_directory, 1)
    predecessor = _read(_path(prior_plan, "launch"))
    _launch(prior_plan, predecessor)
    terminal = _read(_path(prior_plan, "terminal"))
    if (
        set(terminal) != {
            "candidate_id", "attempt", "status", "project_id", "backtest_id",
        }
        or terminal.get("candidate_id") != CANDIDATE_ID
        or terminal.get("attempt") != 1
        or terminal.get("status") != "Runtime Error"
        or terminal.get("project_id") != predecessor["project_id"]
        or terminal.get("backtest_id") != predecessor["backtest_id"]
        or _path(prior_plan, "result-valid").exists()
    ):
        _fail("R247 A1 is not an authenticated invalid predecessor")
    return predecessor, terminal


def _require_failed_a2(plan: SnapshotQcPlan) -> tuple[dict, dict]:
    prior_plan = SnapshotQcPlan(plan.organization_id, plan.control_directory, 2)
    predecessor = _read(_path(prior_plan, "launch"))
    _launch(prior_plan, predecessor)
    first, _ = _require_failed_a1(plan)
    terminal = _read(_path(prior_plan, "terminal"))
    if (
        predecessor.get("project_id") != PROJECT_ID_A3
        or first.get("project_id") != PROJECT_ID_A3
        or predecessor.get("backtest_id") == first.get("backtest_id")
        or set(terminal) != {
            "candidate_id", "attempt", "status", "project_id", "backtest_id",
        }
        or terminal.get("candidate_id") != CANDIDATE_ID
        or terminal.get("attempt") != 2
        or terminal.get("status") != "Runtime Error"
        or terminal.get("project_id") != PROJECT_ID_A3
        or terminal.get("backtest_id") != predecessor["backtest_id"]
        or _path(prior_plan, "result-valid").exists()
    ):
        _fail("R247 A2 is not an authenticated invalid predecessor in the fixed project")
    return predecessor, first


def poll_status_once(plan: SnapshotQcPlan, launch: dict, api) -> str:
    """Read only exact identity/status, with statistics disabled."""
    _launch(plan, launch)
    _client(api)
    terminal = _path(plan, "terminal")
    if terminal.exists():
        return _read(terminal)["status"]
    response = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = response.get("backtests")
    if type(rows) is not list or response.get("count", len(rows)) != len(rows):
        _fail("R247 status inventory changed")
    matches = [row for row in rows if type(row) is dict
               and row.get("backtestId") == launch["backtest_id"]]
    if len(matches) != 1:
        _fail("R247 exact status is absent")
    row = matches[0]
    status = row.get("status")
    if (
        row.get("name") != launch["backtest_name"]
        or ("projectId" in row and row["projectId"] != launch["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("R247 backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write(terminal, {
            "candidate_id": CANDIDATE_ID, "attempt": plan.attempt,
            "status": status, "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


def _parse_meta_response(response: dict, plan: SnapshotQcPlan, launch: dict) -> dict:
    """Ignore standard QC statistics and retain only bounded input metadata."""
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != launch["backtest_name"]
        or backtest.get("status") != "Completed."
    ):
        _fail("R247 result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict:
        _fail("R247 custom statistic is absent")
    value = statistics.get(META_NAME)
    if type(value) is not str or not value.isascii():
        _fail("R247 metadata is not ASCII")
    raw = value.encode("ascii")
    if not 0 < len(raw) <= MAX_META_BYTES:
        _fail("R247 metadata byte bound changed")
    try:
        meta = json.loads(raw)
    except ValueError:
        raise FreshSnapshotSubmissionError("R247 metadata is not JSON") from None
    if type(meta) is not dict or _canonical(meta) != raw or set(meta) != {
        "schema", "object_store_key", "canonical_sha256", "compressed_sha256",
        "canonical_byte_count", "compressed_byte_count",
    }:
        _fail("R247 metadata schema or encoding changed")
    canonical_digest = meta["canonical_sha256"]
    if (
        meta["schema"] != snapshot.SCHEMA
        or type(canonical_digest) is not str or _HEX.fullmatch(canonical_digest) is None
        or type(meta["compressed_sha256"]) is not str
        or _HEX.fullmatch(meta["compressed_sha256"]) is None
        or meta["object_store_key"] != (
            snapshot.PREFIX + DECISION_SESSION + "/" + canonical_digest + ".json.gz"
        )
        or type(meta["canonical_byte_count"]) is not int
        or not 0 < meta["canonical_byte_count"] <= snapshot.MAX_CANONICAL_BYTES
        or type(meta["compressed_byte_count"]) is not int
        or not 0 < meta["compressed_byte_count"] <= snapshot.MAX_COMPRESSED_BYTES
    ):
        _fail("R247 metadata identity, digest, or bounds changed")
    return meta


def read_meta_once(plan: SnapshotQcPlan, launch: dict, api) -> dict:
    """One bounded result request; no logs, orders, returns, or raw input."""
    _launch(plan, launch)
    terminal = _read(_path(plan, "terminal"))
    if (
        terminal.get("status") != "Completed."
        or terminal.get("project_id") != launch["project_id"]
        or terminal.get("backtest_id") != launch["backtest_id"]
    ):
        _fail("R247 run did not complete exactly")
    _client(api)
    _write(_path(plan, "result-read-claim"), {
        "candidate_id": CANDIDATE_ID, "attempt": plan.attempt,
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
        "custom_statistic_name": META_NAME,
    })
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"], "backtestId": launch["backtest_id"],
    })
    meta = _parse_meta_response(response, plan, launch)
    _write(_path(plan, "result-valid"), {
        "candidate_id": CANDIDATE_ID, "attempt": plan.attempt,
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
        "source_manifest_sha256": launch["source_manifest_sha256"],
        "meta_sha256": _digest(_canonical(meta)), "meta": meta,
        "point_in_time_vendor_availability_proven": False,
        "decision_ready": False,
    })
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R247 private input-only QC diagnostic")
    parser.add_argument("action", choices=("plan", "launch", "status", "read-meta"))
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--attempt", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--owner-waiver-id")
    args = parser.parse_args(argv)
    plan = SnapshotQcPlan(args.organization_id, args.control_directory, args.attempt)
    if args.action == "plan":
        print(json.dumps(preview_plan(plan), sort_keys=True))
    elif args.action == "launch":
        # Reject an absent/out-of-scope waiver before constructing a client
        # or reading environment credentials.
        _launch_authority(plan, owner_waiver_id=args.owner_waiver_id)
        print(json.dumps(prepare_and_launch_once(
            plan, production_client(), owner_waiver_id=args.owner_waiver_id,
        ), sort_keys=True))
    else:
        launch = _read(_path(plan, "launch"))
        if args.action == "status":
            print(poll_status_once(plan, launch, production_client()))
        else:
            print(json.dumps(read_meta_once(plan, launch, production_client()), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
