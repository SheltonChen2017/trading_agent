"""Offline-first, input-only R247 QC submission; no action occurs on import.

Only A1 is implemented. A failed A1 consumes its claim; A2/A3 require a
prospective source/permit change in this same project, never a fresh project.
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
META_NAME = "ARV2_FRESH_SIX_INPUT_META"
WAIVER_SCHEMA = "arv2-r247-fresh-six-input-exact-owner-waiver-v1"
# Derived candidate binding under the owner's standing exploratory waiver
# recorded in lane sections 191/192/195; not a new owner statement.
WAIVER_ID = "ARV2-OWNER-STANDING-EXPLORATORY-R247A1-INPUT-ONLY-SIGNATURE-WAIVER"
RUNTIME_SHA256 = "6c386957b25b83d6a5f6333cfa699ae07e0808b965a5a9184059becd992e529f"
MAIN_SHA256 = "6138e86c6589e88f26f1cfddb646d46d692d8e412fe6b26ef09b2df4fa1f955e"
SOURCE_MANIFEST_SHA256 = "3954de79a3398e900a78e6c2f0330ff9cdda370ade3570e41dbe50380684b381"
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


def _files() -> tuple[tuple[str, bytes], ...]:
    """Read the exact committed runtime, then authenticate generated main."""
    runtime = Path(snapshot.__file__)
    try:
        source = runtime.read_bytes()
        main = snapshot.main_source(DECISION_SESSION).encode("ascii")
    except (OSError, UnicodeError, ValueError) as exc:
        raise FreshSnapshotSubmissionError("R247 source is unavailable") from exc
    files = tuple(sorted((
        ("fresh_six_universe_snapshot.py", source), ("main.py", main),
    )))
    if (
        _digest(source) != RUNTIME_SHA256 or _digest(main) != MAIN_SHA256
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
        or type(plan.attempt) is not int or plan.attempt != 1
    ):
        _fail("R247 permits only frozen A1 in an absolute control directory")
    files = _files()
    inventory = [
        {"path": path, "sha256": _digest(raw), "bytes": len(raw)}
        for path, raw in files
    ]
    manifest_sha = _digest(_canonical(inventory))
    if manifest_sha != SOURCE_MANIFEST_SHA256:
        _fail("R247 two-file source manifest changed")
    return {
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "decision_session": DECISION_SESSION,
        "project_name": PROJECT_NAME, "backtest_name": BACKTEST_NAME,
        "source_manifest_sha256": manifest_sha, "source_files": inventory,
        "custom_statistic_name": META_NAME,
        "maximum_attempts_same_project": 3,
        "implemented_attempts": [1],
        "quantconnect_io_performed": False,
    }


def render_owner_waiver_payload(plan: SnapshotQcPlan) -> bytes:
    """Bind the standing exploratory waiver to only this exact input probe."""
    preview = preview_plan(plan)
    return _canonical({
        "schema": WAIVER_SCHEMA,
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": WAIVER_ID,
        "action": "one_private_input_only_snapshot_backtest_launch",
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "organization_id_sha256": _digest(plan.organization_id.encode("ascii")),
        "control_directory": str(plan.control_directory),
        "decision_session": DECISION_SESSION,
        "project_name": PROJECT_NAME, "backtest_name": BACKTEST_NAME,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "source_files": preview["source_files"],
        "custom_statistic_name": META_NAME,
        "mutating_endpoint_budget": {
            "projects/create": 1, "files/delete": 1,
            "files/update": 1, "files/create": 1,
            "compile/create": 1, "backtests/create": 1,
        },
        "maximum_attempts_same_project": 3,
        "maximum_backtest_submissions_this_waiver": 1,
        "bounded_meta_result_read_authorized": True,
        "object_store_download_authorized": False,
        "prices_returns_orders_authorized": False,
        "paper_live_broker_trading_authorized": False,
    })


def _launch_authority(
    plan: SnapshotQcPlan, *, owner_waiver_id: str | None,
) -> dict[str, str]:
    if type(owner_waiver_id) is not str or owner_waiver_id != WAIVER_ID:
        _fail("R247 standing owner waiver does not cover this candidate")
    return {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": WAIVER_SCHEMA,
        "owner_launch_waiver_id": WAIVER_ID,
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
        return _CONTROL_DIRECTORY(plan) / f"{CANDIDATE_ID}-A1-{suffix}.json"
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


def prepare_and_launch_once(
    plan: SnapshotQcPlan, api, *, owner_waiver_id: str | None = None,
) -> dict[str, object]:
    """One exact-waived A1, one fresh private project, exact source, one launch."""
    preview = preview_plan(plan)
    permit = _launch_authority(plan, owner_waiver_id=owner_waiver_id)
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
    readback = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(readback) is not list or len(readback) != 2:
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
        if rendered != raw or _digest(rendered) != next(
            item["sha256"] for item in preview["source_files"] if item["path"] == path
        ):
            _fail("R247 source readback bytes changed")
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
        _fail("R247 compile poll budget exhausted; A1 is consumed")
    if state["state"] == "BuildError":
        _write(_path(plan, "terminal"), {
            "candidate_id": CANDIDATE_ID, "attempt": 1,
            "status": "BuildError", "project_id": project_id,
            "compile_id": compile_id,
        })
        _fail("R247 compile failed; A1 is consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": BACKTEST_NAME,
    }).get("backtest")
    if type(launched) is not dict:
        _fail("R247 launch response changed")
    backtest_id = launched.get("backtestId")
    if (
        type(backtest_id) is not str or _ID.fullmatch(backtest_id) is None
        or launched.get("projectId") != project_id
        or launched.get("name") != BACKTEST_NAME
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("R247 backtest launch identity changed")
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


def _launch(plan: SnapshotQcPlan, launch: dict) -> None:
    preview = preview_plan(plan)
    claim = _read(_path(plan, "claim"))
    if _read(_path(plan, "launch")) != launch or (
        launch.get("candidate_id") != CANDIDATE_ID
        or launch.get("attempt") != 1
        or launch.get("decision_session") != DECISION_SESSION
        or launch.get("project_name") != PROJECT_NAME
        or launch.get("backtest_name") != BACKTEST_NAME
        or launch.get("source_manifest_sha256") != preview["source_manifest_sha256"]
        or type(launch.get("project_id")) is not int
        or type(launch.get("backtest_id")) is not str
        or _ID.fullmatch(launch["backtest_id"]) is None
    ):
        _fail("R247 launch receipt changed")
    expected = _launch_authority(plan, owner_waiver_id=WAIVER_ID)
    if any(launch.get(key) != value for key, value in expected.items()):
        _fail("R247 launch waiver receipt changed")
    if (
        claim.get("candidate_id") != CANDIDATE_ID
        or claim.get("attempt") != 1
        or claim.get("decision_session") != DECISION_SESSION
        or claim.get("project_name") != PROJECT_NAME
        or claim.get("source_manifest_sha256") != preview["source_manifest_sha256"]
        or any(claim.get(key) != value for key, value in expected.items())
    ):
        _fail("R247 launch and claim authority differ")


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
        row.get("name") != BACKTEST_NAME
        or ("projectId" in row and row["projectId"] != launch["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("R247 backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write(terminal, {
            "candidate_id": CANDIDATE_ID, "attempt": 1,
            "status": status, "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


def _parse_meta_response(response: dict, launch: dict) -> dict:
    """Ignore standard QC statistics and retain only bounded input metadata."""
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != BACKTEST_NAME
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
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
        "custom_statistic_name": META_NAME,
    })
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"], "backtestId": launch["backtest_id"],
    })
    meta = _parse_meta_response(response, launch)
    _write(_path(plan, "result-valid"), {
        "candidate_id": CANDIDATE_ID, "attempt": 1,
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
    parser.add_argument("--owner-waiver-id")
    args = parser.parse_args(argv)
    plan = SnapshotQcPlan(args.organization_id, args.control_directory)
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
