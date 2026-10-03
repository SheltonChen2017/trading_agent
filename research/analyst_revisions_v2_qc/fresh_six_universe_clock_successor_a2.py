"""R279 A2: same-project correction for Lean's Object Store key grammar.

R279 A1 proved the 09:20 callback but failed at SaveBytes: Lean's
LocalObjectStore accepts at most one dot in a key, while ``.json.gz`` had
two.  This host-only adapter derives A2 from A1's pinned two-file source,
changes only that suffix to ``.gz``, authenticates the failed predecessor,
and spends exactly one further attempt in the *same* private project.

The result surface is one bounded input metadata statistic. There are no
orders, prices, return reads, paper actions, or side effects on import.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from . import fresh_six_universe_clock_successor as a1
from . import fresh_six_universe_snapshot as snapshot
from . import six_universe_coverage_submission as boundary


class FreshClockA2Error(a1.FreshClockSubmissionError):
    """A2 source, predecessor, private project, or result was refused."""


PROJECT_ID = 37163330
BACKTEST_NAME = "ARV2 R279A2 fresh six supported key 20260928"
WAIVER_ID = "ARV2-OWNER-STANDING-EXPLORATORY-R279A2-INPUT-ONLY-SIGNATURE-WAIVER"
WAIVER_SCHEMA = "arv2-r279a2-fresh-six-key-exact-owner-waiver-v1"
RUNTIME_SHA256 = "6b2d2f4d03d2b7e749c112f053f45685a21b4f9f69359130ac64551b1792047a"
SOURCE_MANIFEST_SHA256 = "440b6e7ccfa561668e2ce40a8e737d4ab2c1529e40cd149f1439b382004755f6"
PREDECESSOR_BACKTEST_ID = "941242b2425d5857bbdc57c5468ccaf9"
_KEY_SUFFIX = ".gz"
_OLD_ANCHOR = b'key = PREFIX + self.decision_session + "/" + digest + ".json.gz"'
_NEW_ANCHOR = b'key = PREFIX + self.decision_session + "/" + digest + ".gz"'
_LEAN_KEY_RE = re.compile(r"^\.?[a-zA-Z0-9\\/_#\-\$= ]+\.?[a-zA-Z0-9]*\Z")


def _fail(message: str) -> None:
    raise FreshClockA2Error(message)


def _prior_plan(plan: a1.FreshClockPlan) -> a1.FreshClockPlan:
    return a1.FreshClockPlan(plan.organization_id, plan.control_directory, 1)


def _path(plan: a1.FreshClockPlan, suffix: str) -> Path:
    if type(plan.attempt) is not int or plan.attempt != 2:
        _fail("R279 A2 exact attempt changed")
    try:
        return a1._CONTROL_DIRECTORY(plan) / f"R279-A2-{suffix}.json"
    except boundary.CoverageQcSubmissionError as exc:
        raise FreshClockA2Error("R279 A2 private control directory is unavailable") from exc


def _files() -> tuple[tuple[str, bytes], ...]:
    prior = dict(a1._files())
    runtime = prior["fresh_six_universe_snapshot.py"]
    if runtime.count(_OLD_ANCHOR) != 1 or _NEW_ANCHOR in runtime:
        _fail("R279 A1 Object Store key anchor changed")
    runtime = runtime.replace(_OLD_ANCHOR, _NEW_ANCHOR)
    if a1._digest(runtime) != RUNTIME_SHA256:
        _fail("R279 A2 runtime source changed")
    compile(runtime, "fresh_six_universe_snapshot.py", "exec")
    files = tuple(sorted((
        ("fresh_six_universe_snapshot.py", runtime),
        ("main.py", prior["main.py"]),
    )))
    return files


def preview_plan(plan: a1.FreshClockPlan) -> dict[str, object]:
    if (
        type(plan) is not a1.FreshClockPlan
        or type(plan.organization_id) is not str
        or a1._ORG.fullmatch(plan.organization_id) is None
        or type(plan.control_directory) is not type(Path())
        or not plan.control_directory.is_absolute()
        or ".." in plan.control_directory.parts
        or type(plan.attempt) is not int or plan.attempt != 2
    ):
        _fail("R279 A2 plan identity changed")
    files = _files()
    inventory = [
        {"path": path, "sha256": a1._digest(raw), "bytes": len(raw)}
        for path, raw in files
    ]
    if (
        a1._digest(a1._canonical(inventory)) != SOURCE_MANIFEST_SHA256
        or any(not 0 < len(raw) <= a1.MAX_SOURCE_FILE_BYTES or not raw.isascii()
               for _, raw in files)
    ):
        _fail("R279 A2 source manifest changed")
    # LocalObjectStore.SaveBytes has one optional dot only. The predecessor's
    # two-dot suffix was rejected; slashes and hyphens were not the cause.
    key = snapshot.PREFIX + a1.DECISION_SESSION + "/" + "a" * 64 + _KEY_SUFFIX
    if _LEAN_KEY_RE.fullmatch(key) is None:
        _fail("R279 A2 Object Store key grammar changed")
    return {
        "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
        "decision_session": a1.DECISION_SESSION,
        "project_id": PROJECT_ID, "project_name": a1.PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "predecessor_backtest_id": PREDECESSOR_BACKTEST_ID,
        "predecessor_source_manifest_sha256": a1.SOURCE_MANIFEST_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_files": inventory, "custom_statistic_name": a1.META_NAME,
        "maximum_attempts_same_project": 3,
        "implemented_attempts": [1, 2], "quantconnect_io_performed": False,
    }


def render_owner_waiver_payload(plan: a1.FreshClockPlan) -> bytes:
    preview = preview_plan(plan)
    return a1._canonical({
        "schema": WAIVER_SCHEMA,
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": WAIVER_ID,
        "action": "one_private_input_only_clock_key_correction_backtest_launch",
        "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
        "organization_id_sha256": a1._digest(plan.organization_id.encode("ascii")),
        "control_directory": str(plan.control_directory),
        "decision_session": a1.DECISION_SESSION,
        "project_id": PROJECT_ID, "project_name": a1.PROJECT_NAME,
        "backtest_name": BACKTEST_NAME,
        "predecessor_backtest_id": PREDECESSOR_BACKTEST_ID,
        "predecessor_source_manifest_sha256": a1.SOURCE_MANIFEST_SHA256,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "source_files": preview["source_files"],
        "custom_statistic_name": a1.META_NAME,
        "mutating_endpoint_budget": {
            "files/update": 1, "compile/create": 1, "backtests/create": 1,
        },
        "maximum_attempts_same_project": 3,
        "maximum_backtest_submissions_this_waiver": 1,
        "bounded_meta_result_read_authorized": True,
        "object_store_download_authorized": False,
        "clock_subscription_price_values_authorized": False,
        "prices_returns_orders_authorized": False,
        "paper_live_broker_trading_authorized": False,
    })


def _authority(plan: a1.FreshClockPlan, owner_waiver_id: str | None) -> dict[str, str]:
    if type(owner_waiver_id) is not str or owner_waiver_id != WAIVER_ID:
        _fail("R279 A2 standing owner waiver changed")
    return {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": WAIVER_SCHEMA,
        "owner_launch_waiver_id": WAIVER_ID,
        "owner_waived_payload_sha256": a1._digest(render_owner_waiver_payload(plan)),
    }


def _predecessor(plan: a1.FreshClockPlan) -> dict:
    prior = _prior_plan(plan)
    launch = a1._read(a1._path(prior, "launch"))
    a1._launch_record(prior, launch)
    terminal = a1._terminal(prior, launch)
    if (
        launch.get("project_id") != PROJECT_ID
        or launch.get("backtest_id") != PREDECESSOR_BACKTEST_ID
        or terminal.get("status") != "Runtime Error"
        or a1._path(prior, "result-valid").exists()
    ):
        _fail("R279 A1 is not the exact invalid predecessor")
    return launch


def _project_and_files(api, plan: a1.FreshClockPlan, prior: dict) -> None:
    response = a1._post(api, "projects/read", {"projectId": PROJECT_ID})
    if a1._project(response, plan) != PROJECT_ID:
        _fail("R279 A2 private predecessor project changed")
    row = response["projects"][0]
    collaborators = row.get("collaborators")
    if (
        row.get("owner") is not True or row.get("codeRunning") is not False
        or row.get("public", False) is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True
               for item in collaborators)
    ):
        _fail("R279 A2 project is not private and idle")
    a1._require_source_readback(api, PROJECT_ID, a1._files())
    response = a1._post(api, "backtests/list", {
        "projectId": PROJECT_ID, "includeStatistics": False,
    })
    rows = response.get("backtests")
    if (
        type(rows) is not list or len(rows) != 1
        or response.get("count", 1) != 1
        or type(rows[0]) is not dict
        or rows[0].get("projectId", PROJECT_ID) != PROJECT_ID
        or rows[0].get("backtestId") != prior["backtest_id"]
        or rows[0].get("name") != a1.BACKTEST_NAME
        or rows[0].get("status") != "Runtime Error"
    ):
        _fail("R279 A2 predecessor QC run inventory changed")


def _launch_record(plan: a1.FreshClockPlan, launch: dict) -> None:
    preview = preview_plan(plan)
    permit = _authority(plan, WAIVER_ID)
    prior = _predecessor(plan)
    claim = a1._read(_path(plan, "claim"))
    if a1._read(_path(plan, "launch")) != launch or (
        launch.get("candidate_id") != a1.CANDIDATE_ID
        or launch.get("attempt") != 2
        or launch.get("decision_session") != a1.DECISION_SESSION
        or launch.get("project_id") != PROJECT_ID
        or launch.get("project_name") != a1.PROJECT_NAME
        or launch.get("backtest_name") != BACKTEST_NAME
        or launch.get("source_manifest_sha256") != SOURCE_MANIFEST_SHA256
        or launch.get("predecessor_backtest_id") != prior["backtest_id"]
        or launch.get("predecessor_source_manifest_sha256") != a1.SOURCE_MANIFEST_SHA256
        or type(launch.get("backtest_id")) is not str
        or a1._ID.fullmatch(launch["backtest_id"]) is None
        or launch["backtest_id"] == prior["backtest_id"]
        or any(launch.get(key) != value for key, value in permit.items())
        or claim.get("candidate_id") != a1.CANDIDATE_ID
        or claim.get("attempt") != 2
        or claim.get("project_id") != PROJECT_ID
        or claim.get("source_manifest_sha256") != preview["source_manifest_sha256"]
        or claim.get("predecessor_backtest_id") != prior["backtest_id"]
        or claim.get("predecessor_source_manifest_sha256") != a1.SOURCE_MANIFEST_SHA256
        or any(claim.get(key) != value for key, value in permit.items())
    ):
        _fail("R279 A2 launch or claim authority changed")


def prepare_and_launch_once(
    plan: a1.FreshClockPlan, api, *, owner_waiver_id: str | None = None,
) -> dict[str, object]:
    """Update only the runtime in A1's project, then compile/launch once."""
    preview = preview_plan(plan)
    permit = _authority(plan, owner_waiver_id)
    files = _files()
    a1._client(api)
    if _path(plan, "claim").exists():
        _fail("R279 A2 was already claimed")
    prior = _predecessor(plan)
    a1._post(api, "authenticate", {})
    _project_and_files(api, plan, prior)
    a1._write(_path(plan, "claim"), {
        **permit, "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
        "decision_session": a1.DECISION_SESSION,
        "project_id": PROJECT_ID, "project_name": a1.PROJECT_NAME,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "predecessor_backtest_id": prior["backtest_id"],
        "predecessor_source_manifest_sha256": a1.SOURCE_MANIFEST_SHA256,
    })
    runtime = dict(files)["fresh_six_universe_snapshot.py"]
    a1._post(api, "files/update", {
        "projectId": PROJECT_ID,
        "name": "fresh_six_universe_snapshot.py",
        "content": runtime.decode("ascii"),
    })
    a1._require_source_readback(api, PROJECT_ID, files)
    response = a1._post(api, "compile/create", {"projectId": PROJECT_ID})
    compile_id = response.get("compileId")
    if type(compile_id) is not str or a1._ID.fullmatch(compile_id) is None:
        _fail("R279 A2 compile identity changed")
    for poll in range(120):
        state = a1._post(api, "compile/read", {
            "projectId": PROJECT_ID, "compileId": compile_id,
        })
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError",
        }:
            _fail("R279 A2 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("R279 A2 compile poll budget exhausted; A2 is consumed")
    if state["state"] == "BuildError":
        a1._write(_path(plan, "terminal"), {
            "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
            "status": "BuildError", "project_id": PROJECT_ID,
            "compile_id": compile_id,
        })
        _fail("R279 A2 compile failed; A2 is consumed")
    launched = a1._post(api, "backtests/create", {
        "projectId": PROJECT_ID, "compileId": compile_id,
        "backtestName": BACKTEST_NAME,
    }).get("backtest")
    if type(launched) is not dict:
        _fail("R279 A2 launch response changed")
    backtest_id = launched.get("backtestId")
    if (
        type(backtest_id) is not str or a1._ID.fullmatch(backtest_id) is None
        or backtest_id == prior["backtest_id"]
        or launched.get("projectId") != PROJECT_ID
        or launched.get("name") != BACKTEST_NAME
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("R279 A2 backtest launch identity changed")
    receipt = {
        **permit, "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
        "decision_session": a1.DECISION_SESSION,
        "project_id": PROJECT_ID, "project_name": a1.PROJECT_NAME,
        "compile_id": compile_id, "backtest_id": backtest_id,
        "backtest_name": BACKTEST_NAME,
        "source_manifest_sha256": preview["source_manifest_sha256"],
        "predecessor_backtest_id": prior["backtest_id"],
        "predecessor_source_manifest_sha256": a1.SOURCE_MANIFEST_SHA256,
    }
    a1._write(_path(plan, "launch"), receipt)
    return receipt


def poll_status_once(plan: a1.FreshClockPlan, launch: dict, api) -> str:
    _launch_record(plan, launch)
    a1._client(api)
    terminal_path = _path(plan, "terminal")
    if terminal_path.exists():
        terminal = a1._read(terminal_path)
        if (
            set(terminal) != {
                "candidate_id", "attempt", "status", "project_id", "backtest_id",
            }
            or terminal.get("candidate_id") != a1.CANDIDATE_ID
            or terminal.get("attempt") != 2
            or terminal.get("status") not in {"Completed.", "Runtime Error"}
            or terminal.get("project_id") != PROJECT_ID
            or terminal.get("backtest_id") != launch["backtest_id"]
        ):
            _fail("R279 A2 terminal identity changed")
        return terminal["status"]
    response = a1._post(api, "backtests/list", {
        "projectId": PROJECT_ID, "includeStatistics": False,
    })
    rows = response.get("backtests")
    if type(rows) is not list or len(rows) != 2 or response.get("count", 2) != 2:
        _fail("R279 A2 exact status inventory changed")
    expected = {
        PREDECESSOR_BACKTEST_ID: (a1.BACKTEST_NAME, "Runtime Error"),
        launch["backtest_id"]: (BACKTEST_NAME, None),
    }
    if len(expected) != 2 or {row.get("backtestId") for row in rows if type(row) is dict} != set(expected):
        _fail("R279 A2 status run identities changed")
    state = None
    for row in rows:
        if (
            type(row) is not dict
            or row.get("projectId", PROJECT_ID) != PROJECT_ID
            or row.get("name") != expected[row["backtestId"]][0]
        ):
            _fail("R279 A2 status project or name changed")
        if row["backtestId"] == PREDECESSOR_BACKTEST_ID:
            if row.get("status") != "Runtime Error":
                _fail("R279 A2 predecessor terminal status changed")
        else:
            state = row.get("status")
            if state not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}:
                _fail("R279 A2 status changed")
    if state in {"Completed.", "Runtime Error"}:
        a1._write(terminal_path, {
            "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
            "status": state, "project_id": PROJECT_ID,
            "backtest_id": launch["backtest_id"],
        })
    return state


def read_meta_once(plan: a1.FreshClockPlan, launch: dict, api) -> dict:
    """Read one input-only statistic after exact terminal completion."""
    _launch_record(plan, launch)
    if poll_status_once(plan, launch, api) != "Completed.":
        _fail("R279 A2 run did not complete exactly")
    a1._client(api)
    a1._write(_path(plan, "result-read-claim"), {
        "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
        "project_id": PROJECT_ID, "backtest_id": launch["backtest_id"],
        "custom_statistic_name": a1.META_NAME,
    })
    response = a1._post(api, "backtests/read", {
        "projectId": PROJECT_ID, "backtestId": launch["backtest_id"],
    })
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != PROJECT_ID
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != BACKTEST_NAME
        or backtest.get("status") != "Completed."
    ):
        _fail("R279 A2 result identity changed")
    statistics = backtest.get("statistics")
    value = statistics.get(a1.META_NAME) if type(statistics) is dict else None
    if type(value) is not str or not value.isascii():
        _fail("R279 A2 metadata is not ASCII")
    raw = value.encode("ascii")
    if not 0 < len(raw) <= a1.MAX_META_BYTES:
        _fail("R279 A2 metadata byte bound changed")
    try:
        meta = json.loads(raw)
    except ValueError:
        raise FreshClockA2Error("R279 A2 metadata is not JSON") from None
    if type(meta) is not dict or a1._canonical(meta) != raw or set(meta) != {
        "schema", "object_store_key", "canonical_sha256", "compressed_sha256",
        "canonical_byte_count", "compressed_byte_count",
    }:
        _fail("R279 A2 metadata schema or encoding changed")
    digest = meta["canonical_sha256"]
    if (
        meta["schema"] != snapshot.SCHEMA
        or type(digest) is not str or a1._HEX.fullmatch(digest) is None
        or type(meta["compressed_sha256"]) is not str
        or a1._HEX.fullmatch(meta["compressed_sha256"]) is None
        or meta["object_store_key"] != (
            snapshot.PREFIX + a1.DECISION_SESSION + "/" + digest + _KEY_SUFFIX
        )
        or type(meta["canonical_byte_count"]) is not int
        or not 0 < meta["canonical_byte_count"] <= snapshot.MAX_CANONICAL_BYTES
        or type(meta["compressed_byte_count"]) is not int
        or not 0 < meta["compressed_byte_count"] <= snapshot.MAX_COMPRESSED_BYTES
    ):
        _fail("R279 A2 metadata identity, digest, or bounds changed")
    a1._write(_path(plan, "result-valid"), {
        "candidate_id": a1.CANDIDATE_ID, "attempt": 2,
        "project_id": PROJECT_ID, "backtest_id": launch["backtest_id"],
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "meta_sha256": a1._digest(a1._canonical(meta)), "meta": meta,
        "point_in_time_vendor_availability_proven": False,
        "decision_ready": False,
    })
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R279 A2 same-project Object Store key correction")
    parser.add_argument("action", choices=("plan", "launch", "status", "read-meta"))
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--attempt", type=int, default=2)
    parser.add_argument("--owner-waiver-id")
    args = parser.parse_args(argv)
    plan = a1.FreshClockPlan(args.organization_id, args.control_directory, args.attempt)
    if args.action == "plan":
        print(json.dumps(preview_plan(plan), sort_keys=True))
    elif args.action == "launch":
        _authority(plan, args.owner_waiver_id)
        print(json.dumps(prepare_and_launch_once(
            plan, a1.production_client(), owner_waiver_id=args.owner_waiver_id,
        ), sort_keys=True))
    else:
        launch = a1._read(_path(plan, "launch"))
        if args.action == "status":
            print(poll_status_once(plan, launch, a1.production_client()))
        else:
            print(json.dumps(read_meta_once(plan, launch, a1.production_client()), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
