"""R279 A1: a separately versioned, input-only QC pre-open clock probe.

R247 spent all three attempts.  This candidate changes its *clock feed*, not
its seven-source input rules: one extended-hours SPY minute subscription drives
the backtest time loop, but its price is never read.  A completed QC backtest
without the exact 09:20, source-checked, Object-Store-backed custom statistic
is not a valid input result.  This module has no action on import.
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
from . import fresh_six_universe_snapshot_submission as r247
from . import six_universe_coverage_submission as boundary


class FreshClockSubmissionError(ValueError):
    """A source, authority, cloud identity, or one-use result failed."""


CANDIDATE_ID = "R279"
DECISION_SESSION = "2026-09-28"
PROJECT_NAME = "ARV2 R279 FRESH SIX CLOCK 20260928"
BACKTEST_NAME = "ARV2 R279A1 fresh six 0920 clock 20260928"
META_NAME = "ARV2_FRESH_SIX_INPUT_META"
WAIVER_ID = "ARV2-OWNER-STANDING-EXPLORATORY-R279A1-INPUT-ONLY-SIGNATURE-WAIVER"
WAIVER_SCHEMA = "arv2-r279a1-fresh-six-clock-exact-owner-waiver-v1"
RUNTIME_SHA256 = r247.RUNTIME_SHA256_A3
MAIN_SHA256 = "39d319efdcf29c766ef091ba647d576b6c6bc1d4fc4e78629b768a72cbc47232"
SOURCE_MANIFEST_SHA256 = "927bfeca30d72d319a74960533466421f0e16b9145b4bae3d6ae3a13b253986c"
MAX_SOURCE_FILE_BYTES = 64_000
MAX_META_BYTES = 2_048
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DEFAULT_FILES = frozenset({"main.py", "research.ipynb"})

# Host-only I/O collaborators already reviewed by the lane.  The source
# uploaded to QC imports only the frozen R247 A3 runtime, never this adapter.
_CLIENT = boundary._client
_POST = boundary._post
_CONTROL_DIRECTORY = boundary._control_directory
_READ_CONTROL = boundary._read_control
_WRITE_ONCE = boundary._write_once


@dataclass(frozen=True)
class FreshClockPlan:
    organization_id: str
    control_directory: Path
    attempt: int = 1


def _fail(message: str) -> None:
    raise FreshClockSubmissionError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _derived_files() -> tuple[tuple[str, bytes], ...]:
    """Derive A1 from the *authenticated* A3 source without touching R247."""
    prior = dict(r247._files(3))
    source = prior["main.py"].decode("ascii")
    before = (
        "        self._snapshot = FreshSixUniverseSnapshot(self, '2026-09-28')\n"
        "        self._etfs = {}\n"
        "        for ticker in ETFS:\n"
        "            self._etfs[ticker] = Symbol.create(ticker, SecurityType.EQUITY, Market.USA)\n"
    )
    after = (
        "        self._snapshot = FreshSixUniverseSnapshot(self, '2026-09-28')\n"
        "        # Clock only: no price, return, portfolio, or order read.\n"
        "        self._clock_symbol = self.add_equity(\n"
        "            'SPY', Resolution.MINUTE, fill_forward=True,\n"
        "            extended_market_hours=True,\n"
        "        ).symbol\n"
        "        self._etfs = {}\n"
        "        for ticker in ETFS:\n"
        "            self._etfs[ticker] = (self._clock_symbol if ticker == 'SPY'\n"
        "                else Symbol.create(ticker, SecurityType.EQUITY, Market.USA))\n"
    )
    # R247 A3's generated main names 2026-09-25.  Replace exactly its
    # authenticated decision literals before adding the subscription.
    old_session = "'2026-09-25'"
    if source.count(old_session) != 3:
        _fail("R247 A3 decision-session anchors changed")
    source = source.replace(old_session, "'2026-09-28'")
    old_start = "self.set_start_date(2026, 9, 11)"
    if source.count(old_start) != 1:
        _fail("R247 A3 start-date anchor changed")
    source = source.replace(old_start, "self.set_start_date(2026, 9, 14)")
    old_end = "self.set_end_date(2026, 9, 25)"
    if source.count(old_end) != 1:
        _fail("R247 A3 end-date anchor changed")
    source = source.replace(old_end, "self.set_end_date(2026, 9, 28)")
    if source.count(before) != 1:
        _fail("R247 A3 generated-main clock anchor changed")
    source = source.replace(before, after)
    if source.count("self.time_rules.at(9, 20)") != 1:
        _fail("R279 exact decision-clock rule changed")
    compile(source, "main.py", "exec")
    return tuple(sorted((
        ("fresh_six_universe_snapshot.py", prior["fresh_six_universe_snapshot.py"]),
        ("main.py", source.encode("ascii")),
    )))


def _files() -> tuple[tuple[str, bytes], ...]:
    try:
        files = _derived_files()
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        raise FreshClockSubmissionError("R279 source is unavailable") from exc
    observed = dict(files)
    if (
        _digest(observed["fresh_six_universe_snapshot.py"]) != RUNTIME_SHA256
        or _digest(observed["main.py"]) != MAIN_SHA256
        or any(not 0 < len(raw) <= MAX_SOURCE_FILE_BYTES or not raw.isascii()
               for _, raw in files)
    ):
        _fail("R279 frozen source bytes changed")
    return files


def preview_plan(plan: FreshClockPlan) -> dict[str, object]:
    """Offline identity only; attempt 2/3 are deliberately unimplemented."""
    if (
        type(plan) is not FreshClockPlan
        or type(plan.organization_id) is not str
        or _ORG.fullmatch(plan.organization_id) is None
        or type(plan.control_directory) is not type(Path())
        or not plan.control_directory.is_absolute()
        or ".." in plan.control_directory.parts
        or type(plan.attempt) is not int or plan.attempt != 1
    ):
        _fail("R279 implements A1 only; A2/A3 require a prospective correction")
    files = _files()
    inventory = [
        {"path": path, "sha256": _digest(raw), "bytes": len(raw)}
        for path, raw in files
    ]
    manifest = _digest(_canonical(inventory))
    if manifest != SOURCE_MANIFEST_SHA256:
        _fail("R279 two-file source manifest changed")
    return {
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "decision_session": DECISION_SESSION,
        "project_name": PROJECT_NAME, "backtest_name": BACKTEST_NAME,
        "source_manifest_sha256": manifest, "source_files": inventory,
        "custom_statistic_name": META_NAME,
        "maximum_attempts_same_project": 3,
        "implemented_attempts": [1], "quantconnect_io_performed": False,
    }


def render_owner_waiver_payload(plan: FreshClockPlan) -> bytes:
    preview = preview_plan(plan)
    return _canonical({
        "schema": WAIVER_SCHEMA,
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": WAIVER_ID,
        "action": "one_private_input_only_clocked_snapshot_backtest_launch",
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "organization_id_sha256": _digest(plan.organization_id.encode("ascii")),
        "control_directory": str(plan.control_directory),
        "decision_session": DECISION_SESSION,
        "project_name": PROJECT_NAME, "backtest_name": BACKTEST_NAME,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "source_files": preview["source_files"],
        "custom_statistic_name": META_NAME,
        "mutating_endpoint_budget": {
            "projects/create": 1, "files/delete": 1, "files/update": 1,
            "files/create": 1, "compile/create": 1, "backtests/create": 1,
        },
        "maximum_attempts_same_project": 3,
        "maximum_backtest_submissions_this_waiver": 1,
        "bounded_meta_result_read_authorized": True,
        "object_store_download_authorized": False,
        "clock_subscription_price_values_authorized": False,
        "prices_returns_orders_authorized": False,
        "paper_live_broker_trading_authorized": False,
    })


def _authority(plan: FreshClockPlan, owner_waiver_id: str | None) -> dict[str, str]:
    if type(owner_waiver_id) is not str or owner_waiver_id != WAIVER_ID:
        _fail("R279 standing owner waiver does not cover this candidate")
    return {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": WAIVER_SCHEMA,
        "owner_launch_waiver_id": WAIVER_ID,
        "owner_waived_payload_sha256": _digest(render_owner_waiver_payload(plan)),
    }


def production_client():
    return boundary.production_client()


def _client(api) -> None:
    try:
        _CLIENT(api)
    except boundary.CoverageQcSubmissionError:
        raise FreshClockSubmissionError("R279 bounded QC client is unavailable") from None


def _post(api, endpoint: str, payload: dict) -> dict:
    try:
        return _POST(api, endpoint, payload)
    except boundary.CoverageQcSubmissionError:
        raise FreshClockSubmissionError("R279 QC " + endpoint + " failed") from None


def _path(plan: FreshClockPlan, suffix: str) -> Path:
    try:
        return _CONTROL_DIRECTORY(plan) / f"{CANDIDATE_ID}-A1-{suffix}.json"
    except boundary.CoverageQcSubmissionError:
        raise FreshClockSubmissionError("R279 private control directory is unavailable") from None


def _read(path: Path) -> dict:
    try:
        return _READ_CONTROL(path)
    except boundary.CoverageQcSubmissionError:
        raise FreshClockSubmissionError("R279 private control is unavailable") from None


def _write(path: Path, value: dict) -> None:
    try:
        _WRITE_ONCE(path, value)
    except boundary.CoverageQcSubmissionError:
        raise FreshClockSubmissionError("R279 one-use control was already spent") from None


def _project(response: dict, plan: FreshClockPlan) -> int:
    rows = response.get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        _fail("R279 project response changed")
    row = rows[0]
    project_id = row.get("projectId")
    if (
        type(project_id) is not int or project_id <= 0
        or row.get("name") != PROJECT_NAME
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
        or row.get("public", False) is not False
    ):
        _fail("R279 project identity changed")
    return project_id


def _require_source_readback(api, project_id: int, files: tuple[tuple[str, bytes], ...]) -> None:
    observed = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(observed) is not list or len(observed) != len(files):
        _fail("R279 two-file readback inventory changed")
    paths = {}
    for row in observed:
        if (
            type(row) is not dict or type(row.get("name")) is not str
            or type(row.get("content")) is not str
            or row.get("projectId") != project_id or row["name"] in paths
        ):
            _fail("R279 source readback identity changed")
        paths[row["name"]] = row["content"]
    if set(paths) != {path for path, _ in files}:
        _fail("R279 source readback paths changed")
    for path, raw in files:
        try:
            rendered = paths[path].encode("ascii")
        except UnicodeError:
            _fail("R279 source readback is not ASCII")
        if rendered != raw:
            _fail("R279 source readback bytes changed")


def _launch_record(plan: FreshClockPlan, launch: dict) -> None:
    preview = preview_plan(plan)
    permit = _authority(plan, WAIVER_ID)
    claim = _read(_path(plan, "claim"))
    if _read(_path(plan, "launch")) != launch or (
        launch.get("candidate_id") != CANDIDATE_ID
        or launch.get("attempt") != 1
        or launch.get("decision_session") != DECISION_SESSION
        or launch.get("project_name") != PROJECT_NAME
        or launch.get("backtest_name") != BACKTEST_NAME
        or launch.get("source_manifest_sha256") != SOURCE_MANIFEST_SHA256
        or type(launch.get("project_id")) is not int
        or type(launch.get("backtest_id")) is not str
        or _ID.fullmatch(launch["backtest_id"]) is None
        or any(launch.get(key) != value for key, value in permit.items())
        or claim.get("candidate_id") != CANDIDATE_ID
        or claim.get("attempt") != 1
        or claim.get("source_manifest_sha256") != preview["source_manifest_sha256"]
        or any(claim.get(key) != value for key, value in permit.items())
    ):
        _fail("R279 launch or claim authority changed")


def _terminal(plan: FreshClockPlan, launch: dict) -> dict:
    terminal = _read(_path(plan, "terminal"))
    if (
        set(terminal) != {
            "candidate_id", "attempt", "status", "project_id", "backtest_id",
        }
        or terminal.get("candidate_id") != CANDIDATE_ID
        or terminal.get("attempt") != 1
        or terminal.get("status") not in {"Completed.", "Runtime Error"}
        or terminal.get("project_id") != launch["project_id"]
        or terminal.get("backtest_id") != launch["backtest_id"]
    ):
        _fail("R279 terminal identity changed")
    return terminal


def prepare_and_launch_once(
    plan: FreshClockPlan, api, *, owner_waiver_id: str | None = None,
) -> dict[str, object]:
    """Exactly one QC project/compile/backtest; claim before first mutation."""
    preview = preview_plan(plan)
    permit = _authority(plan, owner_waiver_id)
    files = _files()
    _client(api)
    if _path(plan, "claim").exists():
        _fail("R279 A1 was already claimed")
    _post(api, "authenticate", {})
    inventory = _post(api, "projects/read", {}).get("projects")
    if type(inventory) is not list or any(
        type(row) is not dict or row.get("name") == PROJECT_NAME
        for row in inventory
    ):
        _fail("R279 project name is not fresh")
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
        _fail("R279 project readback changed")
    row = verified["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True
               for item in collaborators)
    ):
        _fail("R279 project is not private and idle")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in _DEFAULT_FILES
        for item in initial
    ):
        _fail("R279 fresh-project file inventory changed")
    names = [item["name"] for item in initial]
    if len(set(names)) != len(names) or "main.py" not in names:
        _fail("R279 fresh default main file is absent or duplicated")
    if "research.ipynb" in names:
        _post(api, "files/delete", {"projectId": project_id, "name": "research.ipynb"})
    for path, raw in files:
        _post(api, "files/update" if path == "main.py" else "files/create", {
            "projectId": project_id, "name": path, "content": raw.decode("ascii"),
        })
    _require_source_readback(api, project_id, files)
    compiled = _post(api, "compile/create", {"projectId": project_id})
    compile_id = compiled.get("compileId")
    if type(compile_id) is not str or _ID.fullmatch(compile_id) is None:
        _fail("R279 compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": project_id, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("R279 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("R279 compile poll budget exhausted; A1 is consumed")
    if state["state"] == "BuildError":
        _write(_path(plan, "terminal"), {
            "candidate_id": CANDIDATE_ID, "attempt": 1,
            "status": "BuildError", "project_id": project_id,
            "compile_id": compile_id,
        })
        _fail("R279 compile failed; A1 is consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": BACKTEST_NAME,
    }).get("backtest")
    if type(launched) is not dict:
        _fail("R279 launch response changed")
    backtest_id = launched.get("backtestId")
    if (
        type(backtest_id) is not str or _ID.fullmatch(backtest_id) is None
        or launched.get("projectId") != project_id
        or launched.get("name") != BACKTEST_NAME
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("R279 backtest launch identity changed")
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


def poll_status_once(plan: FreshClockPlan, launch: dict, api) -> str:
    """Read only the exact run's status; no QC statistics or logs."""
    _launch_record(plan, launch)
    _client(api)
    terminal_path = _path(plan, "terminal")
    if terminal_path.exists():
        return _terminal(plan, launch)["status"]
    response = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = response.get("backtests")
    if type(rows) is not list or len(rows) != 1 or response.get("count", 1) != 1:
        _fail("R279 exact status inventory changed")
    row = rows[0]
    if (
        type(row) is not dict or row.get("backtestId") != launch["backtest_id"]
        or row.get("projectId", launch["project_id"]) != launch["project_id"]
        or row.get("name") != BACKTEST_NAME
        or row.get("status") not in {
            "In Queue...", "In Progress...", "Completed.", "Runtime Error",
        }
    ):
        _fail("R279 backtest status identity changed")
    status = row["status"]
    if status in {"Completed.", "Runtime Error"}:
        _write(terminal_path, {
            "candidate_id": CANDIDATE_ID, "attempt": 1,
            "status": status, "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


def _parse_meta_response(response: dict, launch: dict) -> dict:
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != BACKTEST_NAME
        or backtest.get("status") != "Completed."
    ):
        _fail("R279 result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict:
        _fail("R279 custom statistic is absent")
    value = statistics.get(META_NAME)
    if type(value) is not str or not value.isascii():
        _fail("R279 metadata is not ASCII")
    raw = value.encode("ascii")
    if not 0 < len(raw) <= MAX_META_BYTES:
        _fail("R279 metadata byte bound changed")
    try:
        meta = json.loads(raw)
    except ValueError:
        raise FreshClockSubmissionError("R279 metadata is not JSON") from None
    if type(meta) is not dict or _canonical(meta) != raw or set(meta) != {
        "schema", "object_store_key", "canonical_sha256", "compressed_sha256",
        "canonical_byte_count", "compressed_byte_count",
    }:
        _fail("R279 metadata schema or encoding changed")
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
        _fail("R279 metadata identity, digest, or bounds changed")
    return meta


def read_meta_once(plan: FreshClockPlan, launch: dict, api) -> dict:
    """One bounded custom-statistic read; never retain returns/orders/logs."""
    _launch_record(plan, launch)
    terminal = _terminal(plan, launch)
    if terminal["status"] != "Completed.":
        _fail("R279 run did not complete exactly")
    _client(api)
    _write(_path(plan, "result-read-claim"), {
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
        "custom_statistic_name": META_NAME,
    })
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"], "backtestId": launch["backtest_id"],
    })
    meta = _parse_meta_response(response, launch)
    _write(_path(plan, "result-valid"), {
        "candidate_id": CANDIDATE_ID, "attempt": 1,
        "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "meta_sha256": _digest(_canonical(meta)), "meta": meta,
        "point_in_time_vendor_availability_proven": False,
        "decision_ready": False,
    })
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R279 private input-only QC clock diagnostic")
    parser.add_argument("action", choices=("plan", "launch", "status", "read-meta"))
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--owner-waiver-id")
    args = parser.parse_args(argv)
    plan = FreshClockPlan(args.organization_id, args.control_directory, args.attempt)
    if args.action == "plan":
        print(json.dumps(preview_plan(plan), sort_keys=True))
    elif args.action == "launch":
        _authority(plan, args.owner_waiver_id)
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


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
