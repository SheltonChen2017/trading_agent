"""One-use private QC launch and aggregate read for the R184 exploratory tilt.

The separate tilt uses R182's matched stock identities and the same 2x
research-only order-admission bridge. Importing this host module performs no
I/O. A valid R181 A3 and R182 A1 receipt chain precedes its single A1 launch.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from research.quantconnect import QuantConnectClient

from . import accepted_risk_six_universe_order_qc_projection as base_projection
from . import accepted_risk_six_universe_order_qc_runtime as base_runtime
from . import accepted_risk_six_universe_order_tilt_qc_projection as tilt_projection
from . import accepted_risk_six_universe_order_tilt_qc_runtime as tilt_runtime
from . import accepted_risk_six_universe_order_tilt_targets as tilt_targets
from . import six_universe_cap90_submission as cap90


class SixUniverseTiltSubmissionError(ValueError):
    """An exact launch, predecessor, source, or aggregate invariant failed."""


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_PROJECT_NAME = "107 ARV2 SIX CAP90 TILT R184 2021 2025"
_PROJECTION_SHA256 = "8fdb1e051c1e9620c1a126dd9d2bd09c1eb298d9dd8ae1d4e7d07ada61af9afc"
_PROFILE_SHA256 = "e0c77820c37b394a88ab7cfc95370b1ce6218c0860ee264fc52bad9b93ada9b2"
_BACKTEST_NAME = "ARV2 R184A1 six cap90 bridge tilt 2021 2025 " + _PROJECTION_SHA256[:8]
_TOTAL_SOURCE_BYTES = 422_728
_SOURCE_COUNT = 16
_PREDECESSOR_PROJECT_NAME = "105 ARV2 SIX CAP90 MATCHED R182 2021 2025"
_WAIVER_ID = cap90._EXPLORATORY_WAIVER_ID
_WAIVER_SCHEMA = "arv2-six-universe-tilt-exact-owner-waiver-v1"
_CUSTOM_NAMES = tuple(sorted((
    base_runtime.META_STATISTIC_NAME,
    base_runtime.AGGREGATES_STATISTIC_NAME,
)))
_TILT_FIELDS = frozenset({
    "matched_baseline_profile_sha256", "matched_baseline_target_path_sha256",
    "tilt_rank_rule_id", "maximum_stock_weight_change_fraction",
})


@dataclass(frozen=True)
class TiltQcPlan:
    organization_id: str = field(repr=False)
    package_sha256: str
    activation_manifest_sha256: str
    control_directory: Path
    candidate_id: str = "R184"
    attempt: int = 1
    role: str = tilt_targets.TILT_ROLE
    project_name: str = _PROJECT_NAME
    backtest_name: str = _BACKTEST_NAME
    projection_sha256: str = _PROJECTION_SHA256
    profile_sha256: str = _PROFILE_SHA256


def _fail(message: str):
    raise SixUniverseTiltSubmissionError(message)


def _canonical(value: object) -> bytes:
    return cap90._canonical(value)


def _post(api: QuantConnectClient, endpoint: str, payload: dict) -> dict:
    try:
        return cap90._post(api, endpoint, payload)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltSubmissionError(str(exc)) from None


def _client(api: QuantConnectClient) -> None:
    try:
        cap90._client(api)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltSubmissionError(str(exc)) from None


def _control_path(plan: TiltQcPlan, name: str) -> Path:
    if name not in {"claim", "launch", "terminal", "result-read-claim", "result-valid"}:
        _fail("tilt control name is not allowlisted")
    root = plan.control_directory
    if not isinstance(root, Path) or not root.is_absolute():
        _fail("tilt control directory is not absolute")
    try:
        root.mkdir(mode=0o700)
        info = root.stat(follow_symlinks=False)
    except FileExistsError:
        info = root.stat(follow_symlinks=False)
    except OSError:
        _fail("tilt control directory is unavailable")
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        _fail("tilt control directory is not private")
    return root / ("R184-A1-" + name + ".json")


def _read(path: Path) -> dict:
    try:
        return cap90._read_control(path)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltSubmissionError(str(exc)) from None


def _write(path: Path, value: dict) -> None:
    try:
        cap90._write_once(path, value)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltSubmissionError(str(exc)) from None


def preview(plan: TiltQcPlan, projection: object) -> dict:
    """Authenticate the pinned, 16-file R184 A1 source before any QC call."""
    if type(plan) is not TiltQcPlan or (
        plan.candidate_id != "R184" or type(plan.attempt) is not int
        or plan.attempt != 1 or plan.role != tilt_targets.TILT_ROLE
        or plan.project_name != _PROJECT_NAME
        or plan.backtest_name != _BACKTEST_NAME
        or plan.projection_sha256 != _PROJECTION_SHA256
        or plan.profile_sha256 != _PROFILE_SHA256
        or type(plan.organization_id) is not str
        or not _ORG.fullmatch(plan.organization_id)
        or not isinstance(plan.control_directory, Path)
        or not plan.control_directory.is_absolute()
        or any(type(value) is not str or not _HEX.fullmatch(value) for value in (
            plan.package_sha256, plan.activation_manifest_sha256,
        ))
    ):
        _fail("tilt launch plan changed from the exact R184 A1 identity")
    profile = tilt_runtime.require_tilt_profile()
    if (
        type(projection) is not base_projection.AcceptedRiskSixUniverseOrderQcProjection
        or projection.schema != tilt_projection.PROJECTION_SCHEMA
        or projection.role != plan.role
        or projection.variant != tilt_runtime.TILT_VARIANT
        or projection.projection_sha256 != plan.projection_sha256
        or projection.profile_id != profile["profile_id"]
        or projection.profile_sha256 != plan.profile_sha256
        or profile["profile_sha256"] != plan.profile_sha256
        or projection.package_sha256 != plan.package_sha256
        or projection.activation_manifest_sha256 != plan.activation_manifest_sha256
        or type(projection.source_files) is not tuple
        or len(projection.source_files) != _SOURCE_COUNT
        or projection.total_source_byte_count != _TOTAL_SOURCE_BYTES
    ):
        _fail("tilt projection, profile, package, or source size changed")
    files = projection.source_files
    paths = []
    for item in files:
        if (
            type(item.project_path) is not str
            or not cap90._PATH.fullmatch(item.project_path)
            or ".." in Path(item.project_path).parts
            or type(item.source_bytes) is not bytes
            or not 0 < len(item.source_bytes) <= base_projection.MAXIMUM_SOURCE_FILE_BYTES
            or len(item.source_bytes) > 64_000
            or item.byte_count != len(item.source_bytes)
            or hashlib.sha256(item.source_bytes).hexdigest() != item.content_sha256
        ):
            _fail("tilt projected file identity or QC bound changed")
        try:
            item.source_bytes.decode("ascii")
        except UnicodeError:
            _fail("tilt projected source is not ASCII")
        paths.append(item.project_path)
    if (
        tuple(paths) != tuple(sorted(paths)) or len(set(paths)) != _SOURCE_COUNT
        or "main.py" not in paths
        or sum(item.byte_count for item in files) != _TOTAL_SOURCE_BYTES
        or _TOTAL_SOURCE_BYTES + base_projection.MINIMUM_REVIEW_MARGIN_BYTES
        > base_projection.MAXIMUM_TOTAL_SOURCE_BYTES
    ):
        _fail("tilt source closure changed")
    semantic = {
        key: value for key, value in projection.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    if (
        digest != _PROJECTION_SHA256
        or projection.projection_id != (
            "arv2-six-universe-order-tilt-qc-projection-" + digest[:24]
        )
    ):
        _fail("tilt source manifest is not self-authenticating")
    return {
        "candidate_id": "R184", "attempt": 1, "role": plan.role,
        "projection_sha256": plan.projection_sha256,
        "profile_id": profile["profile_id"],
        "profile_sha256": plan.profile_sha256,
        "source_files": tuple((item.project_path, item.content_sha256, item.byte_count) for item in files),
    }


def _require_valid_predecessors(plan: TiltQcPlan) -> str:
    """Bind both predecessors and return R182's authenticated target path."""
    # Reuse the existing R182 gate for R181's exact A3 claim/launch/result chain.
    prior_plan = cap90.Cap90QcPlan(
        candidate_id="R182", attempt=1, role="matched",
        project_name=_PREDECESSOR_PROJECT_NAME,
        backtest_name=(
            "ARV2 R182A1 six cap90 bridge matched 2021 2025 "
            + cap90._R182_BRIDGE_PROJECTION_SHA256[:8]
        ),
        organization_id=plan.organization_id,
        projection_sha256=cap90._R182_BRIDGE_PROJECTION_SHA256,
        profile_sha256=cap90._R182_BRIDGE_PROFILE_SHA256,
        package_sha256=plan.package_sha256,
        activation_manifest_sha256=plan.activation_manifest_sha256,
        control_directory=plan.control_directory,
    )
    try:
        cap90._require_prior_valid_role(prior_plan)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltSubmissionError("tilt R181 A3 is not authenticated valid") from exc
    root = plan.control_directory
    claim = _read(root / "R182-A1-claim.json")
    launch = _read(root / "R182-A1-launch.json")
    terminal = _read(root / "R182-A1-terminal.json")
    read_claim = _read(root / "R182-A1-result-read-claim.json")
    valid = _read(root / "R182-A1-result-valid.json")
    if (
        claim.get("candidate_id") != "R182"
        or claim.get("role") != "matched"
        or claim.get("projection_sha256") != cap90._R182_BRIDGE_PROJECTION_SHA256
        or claim.get("profile_sha256") != cap90._R182_BRIDGE_PROFILE_SHA256
        or type(claim.get("source_files")) is not list
        or len(claim["source_files"]) != 14
        or claim.get("owner_launch_authority_mode") != "exact_exploratory_signature_waiver"
        or claim.get("owner_launch_waiver_id") != _WAIVER_ID
        or claim.get("owner_launch_waiver_schema") != cap90._EXPLORATORY_WAIVER_SCHEMA
        or type(claim.get("owner_waived_payload_sha256")) is not str
        or not _HEX.fullmatch(claim["owner_waived_payload_sha256"])
        or launch.get("candidate_id") != "R182"
        or launch.get("role") != "matched"
        or launch.get("project_name") != _PREDECESSOR_PROJECT_NAME
        or launch.get("backtest_name") != prior_plan.backtest_name
        or launch.get("projection_sha256") != cap90._R182_BRIDGE_PROJECTION_SHA256
        or launch.get("profile_sha256") != cap90._R182_BRIDGE_PROFILE_SHA256
        or any(claim.get(key) != launch.get(key) for key in (
            "owner_launch_authority_mode", "owner_launch_waiver_id",
            "owner_launch_waiver_schema", "owner_waived_payload_sha256",
        ))
        or type(launch.get("project_id")) is not int
        or launch["project_id"] <= 0
        or type(launch.get("backtest_id")) is not str
        or not _ID.fullmatch(launch["backtest_id"])
        or terminal != {
            "candidate_id": "R182", "status": "Completed.",
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        or read_claim != {
            "candidate_id": "R182", "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        or valid != {
            "candidate_id": "R182", "attempt": 1, "run_valid": True,
            "aggregate_sha256": valid.get("aggregate_sha256"),
            "target_path_sha256": valid.get("target_path_sha256"),
            "projection_sha256": cap90._R182_BRIDGE_PROJECTION_SHA256,
            "profile_sha256": cap90._R182_BRIDGE_PROFILE_SHA256,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        or type(valid.get("aggregate_sha256")) is not str
        or not _HEX.fullmatch(valid["aggregate_sha256"])
        or type(valid.get("target_path_sha256")) is not str
        or not _HEX.fullmatch(valid["target_path_sha256"])
    ):
        _fail("tilt R182 A1 is not authenticated valid")
    return valid["target_path_sha256"]


def _waived_launch_payload(
    plan: TiltQcPlan, identity: dict, *, matched_baseline_target_path_sha256: str,
) -> bytes:
    if (
        type(matched_baseline_target_path_sha256) is not str
        or not _HEX.fullmatch(matched_baseline_target_path_sha256)
    ):
        _fail("tilt matched baseline target path identity changed")
    return _canonical({
        "schema": _WAIVER_SCHEMA,
        "action": "one_private_exploratory_order_backtest_launch",
        "candidate_id": "R184", "attempt": 1, "role": plan.role,
        "organization_id_sha256": hashlib.sha256(plan.organization_id.encode("ascii")).hexdigest(),
        "project_name": plan.project_name, "backtest_name": plan.backtest_name,
        "control_directory": str(plan.control_directory),
        "projection_sha256": plan.projection_sha256,
        "profile_sha256": plan.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "matched_baseline_target_path_sha256": (
            matched_baseline_target_path_sha256
        ),
        "source_files_sha256": hashlib.sha256(_canonical(identity["source_files"])).hexdigest(),
        "mutating_endpoint_budget": {
            "projects/create": 1, "files/delete": 1,
            "files/create": _SOURCE_COUNT, "files/update": 1,
            "compile/create": 1, "backtests/create": 1,
        },
        "maximum_backtest_submissions": 1,
        "raw_provider_rows_authorized": False,
        "raw_logs_orders_charts_authorized": False,
        "paper_live_deployment_funded_trading_authorized": False,
    })


def launch_a1(
    plan: TiltQcPlan, projection: object, api: QuantConnectClient, *,
    owner_waiver_id: str,
) -> dict:
    """Use one fresh private project and one QC backtest attempt."""
    identity = preview(plan, projection)
    if type(owner_waiver_id) is not str or owner_waiver_id != _WAIVER_ID:
        _fail("tilt exploratory owner signature waiver does not cover launch")
    matched_path_sha = _require_valid_predecessors(plan)
    _client(api)
    claim_path = _control_path(plan, "claim")
    if claim_path.exists():
        _fail("tilt A1 attempt was already claimed")
    _post(api, "authenticate", {})
    projects = _post(api, "projects/read", {}).get("projects")
    if type(projects) is not list or any(
        type(item) is not dict or item.get("name") == plan.project_name
        for item in projects
    ):
        _fail("tilt project name is not fresh")
    authority = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": _WAIVER_SCHEMA,
        "owner_launch_waiver_id": _WAIVER_ID,
        "owner_waived_payload_sha256": hashlib.sha256(
            _waived_launch_payload(
                plan, identity,
                matched_baseline_target_path_sha256=matched_path_sha,
            )
        ).hexdigest(),
    }
    _write(claim_path, {
        **identity, **authority,
        "matched_baseline_target_path_sha256": matched_path_sha,
    })
    project = _post(api, "projects/create", {
        "name": plan.project_name, "language": "Py",
        "organizationId": plan.organization_id,
    }).get("projects")
    if type(project) is not list or len(project) != 1 or type(project[0]) is not dict:
        _fail("tilt created project response changed")
    project_id = project[0].get("projectId")
    if type(project_id) is not int or project_id <= 0:
        _fail("tilt created project ID changed")
    verified = _post(api, "projects/read", {"projectId": project_id}).get("projects")
    if type(verified) is not list or len(verified) != 1 or type(verified[0]) is not dict:
        _fail("tilt project readback changed")
    row = verified[0]
    collaborators = row.get("collaborators")
    if (
        row.get("projectId") != project_id
        or row.get("name") != plan.project_name
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
        or row.get("owner") is not True
        or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("tilt project is not the private idle project")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in cap90._DEFAULT_FILES
        for item in initial
    ):
        _fail("tilt default file inventory changed")
    initial_names = [item["name"] for item in initial]
    if len(initial_names) != len(set(initial_names)):
        _fail("tilt default source paths duplicated")
    if "research.ipynb" in initial_names:
        _post(api, "files/delete", {"projectId": project_id, "name": "research.ipynb"})
    for item in projection.source_files:
        endpoint = (
            "files/update" if item.project_path == "main.py"
            and "main.py" in initial_names else "files/create"
        )
        _post(api, endpoint, {
            "projectId": project_id, "name": item.project_path,
            "content": item.source_bytes.decode("ascii"),
        })
    _check_uploaded_source(plan, project_id, identity, api)
    started = _post(api, "compile/create", {"projectId": project_id})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("tilt compile identity changed")
    for poll in range(120):
        state = _post(api, "compile/read", {
            "projectId": project_id, "compileId": compile_id,
        })
        if (
            state.get("compileId") != compile_id
            or state.get("state") not in {
                "InQueue", "Building", "BuildSuccess", "BuildError",
            }
        ):
            _fail("tilt compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("tilt compile poll exhausted; A1 remains spent")
    if state["state"] == "BuildError":
        _write(_control_path(plan, "terminal"), {
            "candidate_id": "R184", "status": "BuildError",
            "project_id": project_id, "compile_id": compile_id,
        })
        _fail("tilt compile failed; A1 was consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": plan.backtest_name,
    }).get("backtest")
    if type(launched) is not dict or (
        type(launched.get("backtestId")) is not str
        or not _ID.fullmatch(launched["backtestId"])
        or launched.get("projectId") != project_id
        or launched.get("name") != plan.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("tilt backtest launch identity changed")
    receipt = {
        **identity, **authority,
        "matched_baseline_target_path_sha256": matched_path_sha,
        "project_id": project_id, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": plan.backtest_name,
    }
    receipt.pop("source_files")
    _write(_control_path(plan, "launch"), receipt)
    return receipt


def _check_uploaded_source(plan: TiltQcPlan, project_id: int,
                           identity: dict, api: QuantConnectClient) -> None:
    files = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(files) is not list or len(files) != _SOURCE_COUNT:
        _fail("tilt uploaded source inventory changed")
    observed = {}
    for item in files:
        if (
            type(item) is not dict or item.get("projectId") != project_id
            or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("tilt uploaded file identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {record[0] for record in identity["source_files"]}:
        _fail("tilt uploaded source paths changed")
    for path, digest, size in identity["source_files"]:
        try:
            raw = observed[path].encode("ascii")
        except UnicodeError:
            _fail("tilt uploaded source is not ASCII")
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            _fail("tilt uploaded source bytes changed")


def _match_launch(plan: TiltQcPlan, launch: dict) -> None:
    if type(launch) is not dict or (
        launch.get("candidate_id") != "R184"
        or launch.get("attempt") != 1
        or launch.get("role") != plan.role
        or launch.get("project_name") != plan.project_name
        or launch.get("backtest_name") != plan.backtest_name
        or launch.get("projection_sha256") != plan.projection_sha256
        or launch.get("profile_sha256") != plan.profile_sha256
        or type(launch.get("matched_baseline_target_path_sha256")) is not str
        or not _HEX.fullmatch(launch["matched_baseline_target_path_sha256"])
        or type(launch.get("project_id")) is not int
        or launch["project_id"] <= 0
        or type(launch.get("backtest_id")) is not str
        or not _ID.fullmatch(launch["backtest_id"])
    ):
        _fail("tilt launch receipt differs from the frozen plan")


def poll_status(plan: TiltQcPlan, launch: dict, api: QuantConnectClient) -> str:
    """Read only the exact backtest's terminal or in-progress status."""
    _client(api)
    _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("tilt launch receipt changed")
    terminal_path = _control_path(plan, "terminal")
    if terminal_path.exists():
        return _read(terminal_path)["status"]
    listing = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = listing.get("backtests")
    if type(rows) is not list or listing.get("count", len(rows)) != len(rows):
        _fail("tilt backtest status inventory changed")
    matched = [item for item in rows if type(item) is dict
               and item.get("backtestId") == launch["backtest_id"]]
    if len(matched) != 1:
        _fail("tilt exact backtest status is absent")
    row = matched[0]
    status = row.get("status")
    if (
        row.get("name") != launch["backtest_name"]
        or ("projectId" in row and row["projectId"] != launch["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("tilt backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write(terminal_path, {
            "candidate_id": "R184", "status": status,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


def read_aggregates_once(plan: TiltQcPlan, launch: dict,
                         api: QuantConnectClient) -> dict:
    """Read two canonical custom statistics once after Completed."""
    _client(api)
    _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("tilt launch receipt changed")
    if _read(_control_path(plan, "terminal")) != {
        "candidate_id": "R184", "status": "Completed.",
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    }:
        _fail("tilt exact run did not complete")
    read_path = _control_path(plan, "result-read-claim")
    if read_path.exists():
        _fail("tilt result read was already claimed")
    claim = _read(_control_path(plan, "claim"))
    matched_path_sha = _require_valid_predecessors(plan)
    if (
        type(claim.get("source_files")) is not list
        or len(claim["source_files"]) != _SOURCE_COUNT
        or claim.get("projection_sha256") != plan.projection_sha256
        or claim.get("profile_sha256") != plan.profile_sha256
        or claim.get("matched_baseline_target_path_sha256") != matched_path_sha
        or launch.get("matched_baseline_target_path_sha256") != matched_path_sha
        or claim.get("owner_launch_authority_mode")
        != "exact_exploratory_signature_waiver"
        or claim.get("owner_launch_waiver_schema") != _WAIVER_SCHEMA
        or claim.get("owner_launch_waiver_id") != _WAIVER_ID
        or claim.get("owner_waived_payload_sha256") != hashlib.sha256(
            _waived_launch_payload(
                plan, claim,
                matched_baseline_target_path_sha256=matched_path_sha,
            )
        ).hexdigest()
        or any(claim.get(key) != launch.get(key) for key in (
            "owner_launch_authority_mode", "owner_launch_waiver_schema",
            "owner_launch_waiver_id", "owner_waived_payload_sha256",
        ))
    ):
        _fail("tilt source claim or owner waiver changed")
    _check_uploaded_source(plan, launch["project_id"], claim, api)
    _write(read_path, {
        "candidate_id": "R184", "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    })
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"],
        "backtestId": launch["backtest_id"],
    })
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != launch["backtest_name"]
        or backtest.get("status") != "Completed."
    ):
        _fail("tilt result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or tuple(sorted(
        key for key in statistics
        if type(key) is str and key.startswith("ARV2_SIX_GATE_ORDER_")
    )) != _CUSTOM_NAMES:
        _fail("tilt custom statistic inventory changed")
    try:
        _meta_text, meta = cap90._statistic(statistics[base_runtime.META_STATISTIC_NAME])
        aggregate_text, aggregate = cap90._statistic(
            statistics[base_runtime.AGGREGATES_STATISTIC_NAME]
        )
    except (KeyError, cap90.Cap90QcSubmissionError):
        _fail("tilt custom statistics are not bounded canonical JSON")
    if (
        set(meta) != cap90._META_FIELDS
        or set(aggregate) != cap90._BRIDGE_AGGREGATE_FIELDS | _TILT_FIELDS
        or meta.get("schema") != base_runtime.META_SCHEMA
        or meta.get("role") != plan.role
        or meta.get("profile_id") != launch["profile_id"]
        or meta.get("profile_sha256") != plan.profile_sha256
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("activation_manifest_sha256") != plan.activation_manifest_sha256
        or type(meta.get("package_id")) is not str
        or not _ID.fullmatch(meta["package_id"])
        or type(meta.get("symbol_resolution_id")) is not str
        or not _ID.fullmatch(meta["symbol_resolution_id"])
        or type(meta.get("symbol_resolution_sha256")) is not str
        or not _HEX.fullmatch(meta["symbol_resolution_sha256"])
        or meta.get("result_transport") != "two_bounded_custom_summary_statistics"
        or meta.get("aggregate_schema") != tilt_runtime.TILT_SUMMARY_SCHEMA
        or meta.get("aggregate_sha256") != hashlib.sha256(
            aggregate_text.encode("ascii")
        ).hexdigest()
        or meta.get("raw_provider_rows") is not False
        or meta.get("raw_price_rows") is not False
        or meta.get("raw_order_rows") is not False
        or meta.get("backtest_only") is not True
        or meta.get("preliminary") is not True
        or meta.get("formal") is not False
        or meta.get("trading") is not False
        or aggregate.get("schema") != tilt_runtime.TILT_SUMMARY_SCHEMA
        or aggregate.get("role") != plan.role
        or aggregate.get("profile_id") != launch["profile_id"]
        or aggregate.get("profile_sha256") != plan.profile_sha256
        or aggregate.get("matched_baseline_profile_sha256")
        != tilt_runtime.BASELINE_MATCHED_PROFILE_SHA256
        or aggregate.get("matched_baseline_target_path_sha256") != matched_path_sha
        or aggregate.get("tilt_rank_rule_id") != tilt_targets.TILT_RANK_RULE_ID
        or aggregate.get("maximum_stock_weight_change_fraction") != "0.20"
        or aggregate.get("backtest_only") is not True
        or aggregate.get("preliminary") is not True
        or aggregate.get("formal") is not False
        or any(aggregate.get(key) is not False for key in (
            "live_orders", "paper_orders", "funded_orders", "deployment", "trading",
        ))
        or type(aggregate.get("run_valid")) is not bool
        or type(aggregate.get("execution")) is not dict
        or type(aggregate["execution"].get("run_valid")) is not bool
        or (aggregate["run_valid"] and not aggregate["execution"]["run_valid"])
    ):
        _fail("tilt result lineage, digest, or safety flag changed")
    core = {key: value for key, value in aggregate.items() if key not in _TILT_FIELDS}
    try:
        selected = cap90._project_aggregate(core, bridge=True)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltSubmissionError(str(exc)) from None
    selected.update({key: aggregate[key] for key in _TILT_FIELDS})
    valid = aggregate["run_valid"] is True
    if valid:
        _write(_control_path(plan, "result-valid"), {
            "candidate_id": "R184", "attempt": 1, "run_valid": True,
            "aggregate_sha256": meta["aggregate_sha256"],
            "projection_sha256": plan.projection_sha256,
            "profile_sha256": plan.profile_sha256,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return {"meta": meta, "aggregates": selected, "run_valid": valid}


__all__ = (
    "SixUniverseTiltSubmissionError", "TiltQcPlan", "launch_a1",
    "poll_status", "preview", "read_aggregates_once",
)
