"""One-use private QC launches for the frozen R187/R188/R189 tilt ladder.

This host-only adapter performs no I/O at import. Each percent has an exact
source/profile/project/run pin, a distinct owner-waiver attestation, its own
attempt claim, and at most one bounded aggregate read. The economic source
and predecessor checks are delegated to the existing pinned projections.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from research.quantconnect import QuantConnectClient

from . import accepted_risk_six_universe_order_qc_projection as base_projection
from . import accepted_risk_six_universe_order_qc_runtime as base_runtime
from . import accepted_risk_six_universe_order_tilt40_qc_projection as tilt40_projection
from . import accepted_risk_six_universe_order_tilt_ladder_qc_projection as ladder_projection
from . import six_universe_cap90_submission as cap90
from . import six_universe_tilt80_submission as prior


class SixUniverseTiltLadderSubmissionError(ValueError):
    """An exact source, authority, launch, or result invariant failed."""


@dataclass(frozen=True)
class _Candidate:
    percent: int
    candidate_id: str
    project_name: str
    role: str
    projection_sha256: str
    profile_sha256: str
    source_files_sha256: str
    total_source_bytes: int
    waiver_id: str

    @property
    def backtest_name(self) -> str:
        return (
            f"ARV2 {self.candidate_id}A1 six cap90 bridge tilt{self.percent} "
            f"2021 2025 {self.projection_sha256[:8]}"
        )

    @property
    def waiver_schema(self) -> str:
        return f"arv2-six-universe-tilt{self.percent}-exact-owner-waiver-v1"


# Literal pins are filled from the separately authenticated, preregistered
# projection before launch. They must not be inferred from a QC response.
_CANDIDATES = {
    70: _Candidate(
        70, "R187", "110 ARV2 SIX CAP90 TILT70 R187 2021 2025",
        "matched_revision_tilt70",
        "3203481571307cbad000153542ac9529cb1e4a3ac1bac030f18150b6a22dcbe0",
        "6189373282c0e5652bda0317d0133e1ccc52057116035ed6a51428788d8e31f2",
        "7d068209b38bfdb527e85529b991a9ff30d3638667a99b24fbb1edbaf98b4412",
        422_758, "ARV2-OWNER-2026-09-25-R187A1-TILT70-EXPLORATORY-SIGNATURE-WAIVER",
    ),
    60: _Candidate(
        60, "R188", "111 ARV2 SIX CAP90 TILT60 R188 2021 2025",
        "matched_revision_tilt60",
        "3eed978da51ef82b0de3f44b2f3bb30311e27a8f628ed3f9b6663d902f78fc55",
        "82592bb4c82078496899f2e225c31f6c47a759b93997f464fac731eff99ed875",
        "239398535d2b33f5ccf2e1b156a48a941225a60ffade2bfaca24e82e4f7c7e19",
        422_758, "ARV2-OWNER-2026-09-25-R188A1-TILT60-EXPLORATORY-SIGNATURE-WAIVER",
    ),
    50: _Candidate(
        50, "R189", "112 ARV2 SIX CAP90 TILT50 R189 2021 2025",
        "matched_revision_tilt50",
        "e1f417b2a7e785e558ec0af83297083fa07c0bbc22c930447bb6e0e99a25f2d3",
        "5314cab14e8f50e38998c07dead583eb38b57eefcb0e2ad8768d5681adec116e",
        "566ca01d30590dbd7252c3a4b9bc6301618b1bac7e1721cd827c2001ccdb29ba",
        422_758, "ARV2-OWNER-2026-09-25-R189A1-TILT50-EXPLORATORY-SIGNATURE-WAIVER",
    ),
}

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_SOURCE_COUNT = 16
_PREDECESSOR_TARGET_PATH_SHA256 = (
    "b825663b4dfdee835f1c118a49fdd49e0a8d37387b8045060d77b5b3bbdcadbc"
)
_CUSTOM_NAMES = tuple(sorted((
    base_runtime.META_STATISTIC_NAME,
    base_runtime.AGGREGATES_STATISTIC_NAME,
)))
_TILT_FIELDS = frozenset({
    "matched_baseline_profile_sha256", "matched_baseline_target_path_sha256",
    "tilt_rank_rule_id", "maximum_stock_weight_change_fraction",
})


@dataclass(frozen=True)
class TiltLadderQcPlan:
    percent: int
    organization_id: str
    package_sha256: str
    activation_manifest_sha256: str
    control_directory: Path
    attempt: int = 1

    @property
    def candidate_id(self) -> str:
        return _candidate(self).candidate_id

    @property
    def project_name(self) -> str:
        return _candidate(self).project_name

    @property
    def backtest_name(self) -> str:
        return _candidate(self).backtest_name

    @property
    def role(self) -> str:
        return _candidate(self).role

    @property
    def projection_sha256(self) -> str:
        return _candidate(self).projection_sha256

    @property
    def profile_sha256(self) -> str:
        return _candidate(self).profile_sha256


def _fail(message: str):
    raise SixUniverseTiltLadderSubmissionError(message)


def _canonical(value: object) -> bytes:
    return cap90._canonical(value)


def _candidate(plan: TiltLadderQcPlan) -> _Candidate:
    if type(plan) is not TiltLadderQcPlan or type(plan.percent) is not int:
        _fail("tilt-ladder plan type changed")
    candidate = _CANDIDATES.get(plan.percent)
    if candidate is None or (
        type(plan.attempt) is not int or plan.attempt != 1
        or type(plan.organization_id) is not str
        or not _ORG.fullmatch(plan.organization_id)
        or type(plan.package_sha256) is not str
        or not _HEX.fullmatch(plan.package_sha256)
        or type(plan.activation_manifest_sha256) is not str
        or not _HEX.fullmatch(plan.activation_manifest_sha256)
        or not isinstance(plan.control_directory, Path)
        or not plan.control_directory.is_absolute()
    ):
        _fail("tilt-ladder plan changed from its exact A1 identity")
    return candidate


def _post(api: QuantConnectClient, endpoint: str, payload: dict) -> dict:
    try:
        return cap90._post(api, endpoint, payload)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltLadderSubmissionError(str(exc)) from None


def _client(api: QuantConnectClient) -> None:
    try:
        cap90._client(api)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltLadderSubmissionError(str(exc)) from None


def _control_path(plan: TiltLadderQcPlan, name: str) -> Path:
    candidate = _candidate(plan)
    if name not in {"claim", "launch", "terminal", "result-read-claim", "result-valid"}:
        _fail("tilt-ladder control name is not allowlisted")
    root = plan.control_directory
    try:
        root.mkdir(mode=0o700)
        info = root.stat(follow_symlinks=False)
    except FileExistsError:
        info = root.stat(follow_symlinks=False)
    except OSError:
        _fail("tilt-ladder control directory is unavailable")
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        _fail("tilt-ladder control directory is not private")
    return root / f"{candidate.candidate_id}-A1-{name}.json"


def _read(path: Path) -> dict:
    try:
        return cap90._read_control(path)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltLadderSubmissionError(str(exc)) from None


def _write(path: Path, value: dict) -> None:
    try:
        cap90._write_once(path, value)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltLadderSubmissionError(str(exc)) from None


def preview(plan: TiltLadderQcPlan, projection: object) -> dict:
    """Authenticate all 16 source files before any QC call or attempt claim."""
    candidate = _candidate(plan)
    profile = ladder_projection.require_tilt_ladder_profile(plan.percent)
    if (
        type(projection) is not base_projection.AcceptedRiskSixUniverseOrderQcProjection
        or projection.schema != (
            f"arv2-six-universe-order-tilt{plan.percent}-qc-projection-bridge-v1"
        )
        or projection.role != candidate.role
        or projection.variant != (
            f"cap90_matched_revision_tilt{plan.percent}_admission_bridge_v1"
        )
        or projection.projection_sha256 != candidate.projection_sha256
        or projection.profile_id != profile["profile_id"]
        or projection.profile_sha256 != candidate.profile_sha256
        or profile["profile_sha256"] != candidate.profile_sha256
        or projection.package_sha256 != plan.package_sha256
        or projection.activation_manifest_sha256 != plan.activation_manifest_sha256
        or type(projection.source_files) is not tuple
        or len(projection.source_files) != _SOURCE_COUNT
        or projection.total_source_byte_count != candidate.total_source_bytes
    ):
        _fail("tilt-ladder projection, profile, package, or source size changed")
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
            _fail("tilt-ladder projected file identity or QC bound changed")
        try:
            item.source_bytes.decode("ascii")
        except UnicodeError:
            _fail("tilt-ladder projected source is not ASCII")
        paths.append(item.project_path)
    if (
        tuple(paths) != tuple(sorted(paths)) or len(set(paths)) != _SOURCE_COUNT
        or "main.py" not in paths
        or sum(item.byte_count for item in files) != candidate.total_source_bytes
        or candidate.total_source_bytes + base_projection.MINIMUM_REVIEW_MARGIN_BYTES
        > base_projection.MAXIMUM_TOTAL_SOURCE_BYTES
    ):
        _fail("tilt-ladder source closure changed")
    semantic = {
        key: value for key, value in projection.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    source_manifest = tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in files
    )
    if (
        digest != candidate.projection_sha256
        or projection.projection_id != (
            f"arv2-six-universe-order-tilt{plan.percent}-qc-projection-"
            + digest[:24]
        )
        or hashlib.sha256(_canonical(source_manifest)).hexdigest()
        != candidate.source_files_sha256
    ):
        _fail("tilt-ladder source manifest is not self-authenticating")
    return {
        "candidate_id": candidate.candidate_id, "attempt": 1,
        "role": candidate.role,
        "projection_sha256": candidate.projection_sha256,
        "profile_id": profile["profile_id"],
        "profile_sha256": candidate.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "source_files": source_manifest,
    }


def _require_valid_predecessors(plan: TiltLadderQcPlan) -> str:
    try:
        matched_path_sha = prior._require_valid_predecessors(plan)
    except prior.SixUniverseTilt80SubmissionError as exc:
        raise SixUniverseTiltLadderSubmissionError(str(exc)) from None
    if matched_path_sha != _PREDECESSOR_TARGET_PATH_SHA256:
        _fail("tilt-ladder R182 target path changed from its preregistered pin")
    return matched_path_sha


def _render_waived_launch_payload(
    plan: TiltLadderQcPlan, identity: dict, matched_path_sha: str,
) -> bytes:
    candidate = _candidate(plan)
    if matched_path_sha != _PREDECESSOR_TARGET_PATH_SHA256:
        _fail("tilt-ladder predecessor path changed")
    return _canonical({
        "schema": candidate.waiver_schema,
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": candidate.waiver_id,
        "action": "one_private_exploratory_order_backtest_launch",
        "candidate_id": candidate.candidate_id, "attempt": 1,
        "tilt_percent": plan.percent, "role": candidate.role,
        "organization_id_sha256": hashlib.sha256(
            plan.organization_id.encode("ascii")
        ).hexdigest(),
        "project_id": None, "project_name": candidate.project_name,
        "backtest_name": candidate.backtest_name,
        "control_directory": str(plan.control_directory),
        "projection_sha256": candidate.projection_sha256,
        "profile_id": identity["profile_id"],
        "profile_sha256": candidate.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "matched_baseline_target_path_sha256": matched_path_sha,
        "source_files_sha256": hashlib.sha256(
            _canonical(identity["source_files"])
        ).hexdigest(),
        "mutating_endpoint_budget": {
            "projects/create": 1, "files/delete": 1,
            "files/create": _SOURCE_COUNT, "files/update": 1,
            "compile/create": 1, "backtests/create": 1,
        },
        "maximum_backtest_submissions": 1,
        "aggregate_only_result_read_authorized": True,
        "maximum_result_reads": 1,
        "raw_provider_rows_authorized": False,
        "raw_logs_orders_charts_authorized": False,
        "paper_live_deployment_funded_trading_authorized": False,
    })


def render_owner_waiver_payload(plan: TiltLadderQcPlan, projection: object) -> bytes:
    """Preview the exact candidate-specific waiver for owner and review."""
    identity = preview(plan, projection)
    matched_path_sha = _require_valid_predecessors(plan)
    return _render_waived_launch_payload(plan, identity, matched_path_sha)


def _check_uploaded_source(
    project_id: int, identity: dict, api: QuantConnectClient,
) -> None:
    files = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(files) is not list or len(files) != _SOURCE_COUNT:
        _fail("tilt-ladder uploaded source inventory changed")
    observed = {}
    for item in files:
        if (
            type(item) is not dict or item.get("projectId") != project_id
            or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("tilt-ladder uploaded file identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {row[0] for row in identity["source_files"]}:
        _fail("tilt-ladder uploaded source paths changed")
    for path, digest, size in identity["source_files"]:
        try:
            raw = observed[path].encode("ascii")
        except UnicodeError:
            _fail("tilt-ladder uploaded source is not ASCII")
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            _fail("tilt-ladder uploaded source bytes changed")


def launch_a1(
    plan: TiltLadderQcPlan, projection: object, api: QuantConnectClient, *,
    owner_waiver_id: str,
) -> dict:
    """Claim one A1, upload exact source to a fresh private project, and run."""
    candidate = _candidate(plan)
    identity = preview(plan, projection)
    matched_path_sha = _require_valid_predecessors(plan)
    if type(owner_waiver_id) is not str or owner_waiver_id != candidate.waiver_id:
        _fail("tilt-ladder owner waiver does not cover this candidate")
    authority = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": candidate.waiver_schema,
        "owner_launch_waiver_id": candidate.waiver_id,
        "owner_waived_payload_sha256": hashlib.sha256(
            _render_waived_launch_payload(plan, identity, matched_path_sha)
        ).hexdigest(),
    }
    claim_path = _control_path(plan, "claim")
    if claim_path.exists():
        _fail("tilt-ladder A1 attempt was already claimed")
    _client(api)
    _post(api, "authenticate", {})
    projects = _post(api, "projects/read", {}).get("projects")
    if type(projects) is not list or any(
        type(item) is not dict or item.get("name") == candidate.project_name
        for item in projects
    ):
        _fail("tilt-ladder project name is not fresh")
    _write(claim_path, {
        **identity, **authority,
        "matched_baseline_target_path_sha256": matched_path_sha,
    })
    project = _post(api, "projects/create", {
        "name": candidate.project_name, "language": "Py",
        "organizationId": plan.organization_id,
    }).get("projects")
    if type(project) is not list or len(project) != 1 or type(project[0]) is not dict:
        _fail("tilt-ladder created project response changed")
    project_id = project[0].get("projectId")
    if type(project_id) is not int or project_id <= 0:
        _fail("tilt-ladder created project ID changed")
    verified = _post(api, "projects/read", {"projectId": project_id}).get("projects")
    if type(verified) is not list or len(verified) != 1 or type(verified[0]) is not dict:
        _fail("tilt-ladder project readback changed")
    row = verified[0]
    collaborators = row.get("collaborators")
    if (
        row.get("projectId") != project_id
        or row.get("name") != candidate.project_name
        or row.get("organizationId") != plan.organization_id
        or row.get("language") != "Py"
        or row.get("owner") is not True
        or row.get("codeRunning") is not False
        or type(collaborators) is not list or len(collaborators) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)
    ):
        _fail("tilt-ladder project is not the private idle project")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in cap90._DEFAULT_FILES
        for item in initial
    ):
        _fail("tilt-ladder default file inventory changed")
    initial_names = [item["name"] for item in initial]
    if len(initial_names) != len(set(initial_names)):
        _fail("tilt-ladder default source paths duplicated")
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
    _check_uploaded_source(project_id, identity, api)
    started = _post(api, "compile/create", {"projectId": project_id})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("tilt-ladder compile identity changed")
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
            _fail("tilt-ladder compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("tilt-ladder compile poll exhausted; A1 remains spent")
    if state["state"] == "BuildError":
        _write(_control_path(plan, "terminal"), {
            "candidate_id": candidate.candidate_id, "status": "BuildError",
            "project_id": project_id, "compile_id": compile_id,
        })
        _fail("tilt-ladder compile failed; A1 was consumed")
    launched = _post(api, "backtests/create", {
        "projectId": project_id, "compileId": compile_id,
        "backtestName": candidate.backtest_name,
    }).get("backtest")
    if type(launched) is not dict or (
        type(launched.get("backtestId")) is not str
        or not _ID.fullmatch(launched["backtestId"])
        or launched.get("projectId") != project_id
        or launched.get("name") != candidate.backtest_name
        or launched.get("status") not in {"In Queue...", "In Progress..."}
    ):
        _fail("tilt-ladder backtest launch identity changed")
    receipt = {
        **{key: value for key, value in identity.items() if key != "source_files"},
        **authority,
        "matched_baseline_target_path_sha256": matched_path_sha,
        "project_id": project_id, "project_name": candidate.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": candidate.backtest_name,
    }
    _write(_control_path(plan, "launch"), receipt)
    return receipt


def _match_launch(plan: TiltLadderQcPlan, launch: dict) -> _Candidate:
    candidate = _candidate(plan)
    if type(launch) is not dict or (
        launch.get("candidate_id") != candidate.candidate_id
        or launch.get("attempt") != 1
        or launch.get("role") != candidate.role
        or launch.get("project_name") != candidate.project_name
        or launch.get("backtest_name") != candidate.backtest_name
        or launch.get("projection_sha256") != candidate.projection_sha256
        or launch.get("profile_sha256") != candidate.profile_sha256
        or launch.get("matched_baseline_target_path_sha256")
        != _PREDECESSOR_TARGET_PATH_SHA256
        or type(launch.get("project_id")) is not int or launch["project_id"] <= 0
        or type(launch.get("backtest_id")) is not str
        or not _ID.fullmatch(launch["backtest_id"])
    ):
        _fail("tilt-ladder launch receipt differs from the exact plan")
    return candidate


def poll_status(
    plan: TiltLadderQcPlan, launch: dict, api: QuantConnectClient,
) -> str:
    """Read only exact status, not result statistics or logs."""
    candidate = _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("tilt-ladder launch receipt changed")
    terminal_path = _control_path(plan, "terminal")
    if terminal_path.exists():
        return _read(terminal_path)["status"]
    _client(api)
    listing = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = listing.get("backtests")
    if type(rows) is not list or listing.get("count", len(rows)) != len(rows):
        _fail("tilt-ladder backtest status inventory changed")
    matched = [item for item in rows if type(item) is dict
               and item.get("backtestId") == launch["backtest_id"]]
    if len(matched) != 1:
        _fail("tilt-ladder exact backtest status is absent")
    row = matched[0]
    status = row.get("status")
    if (
        row.get("name") != candidate.backtest_name
        or ("projectId" in row and row["projectId"] != launch["project_id"])
        or status not in {"In Queue...", "In Progress...", "Completed.", "Runtime Error"}
    ):
        _fail("tilt-ladder backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write(terminal_path, {
            "candidate_id": candidate.candidate_id, "status": status,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


def read_aggregates_once(
    plan: TiltLadderQcPlan, launch: dict, api: QuantConnectClient,
) -> dict:
    """Read only exact custom META/AGGREGATES after a completed A1."""
    candidate = _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("tilt-ladder launch receipt changed")
    if _read(_control_path(plan, "terminal")) != {
        "candidate_id": candidate.candidate_id, "status": "Completed.",
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    }:
        _fail("tilt-ladder exact run did not complete")
    read_path = _control_path(plan, "result-read-claim")
    if read_path.exists():
        _fail("tilt-ladder result read was already claimed")
    claim = _read(_control_path(plan, "claim"))
    matched_path_sha = _require_valid_predecessors(plan)
    source_files = claim.get("source_files")
    if (
        claim.get("candidate_id") != candidate.candidate_id
        or claim.get("attempt") != 1
        or claim.get("role") != candidate.role
        or type(source_files) is not list or len(source_files) != _SOURCE_COUNT
        or any(
            type(item) is not list or len(item) != 3
            or type(item[0]) is not str or type(item[1]) is not str
            or type(item[2]) is not int or item[2] <= 0
            for item in source_files
        )
        or hashlib.sha256(_canonical(source_files)).hexdigest()
        != candidate.source_files_sha256
        or claim.get("projection_sha256") != candidate.projection_sha256
        or claim.get("profile_sha256") != candidate.profile_sha256
        or claim.get("package_sha256") != plan.package_sha256
        or claim.get("activation_manifest_sha256") != plan.activation_manifest_sha256
        or claim.get("matched_baseline_target_path_sha256") != matched_path_sha
        or any(claim.get(key) != launch.get(key) for key in (
            "candidate_id", "attempt", "role", "projection_sha256",
            "profile_id", "profile_sha256", "package_sha256",
            "activation_manifest_sha256", "matched_baseline_target_path_sha256",
        ))
    ):
        _fail("tilt-ladder source claim or predecessor changed")
    expected_waiver_sha = hashlib.sha256(_render_waived_launch_payload(
        plan, claim, matched_path_sha,
    )).hexdigest()
    if (
        claim.get("owner_launch_authority_mode")
        != "exact_exploratory_signature_waiver"
        or claim.get("owner_launch_waiver_schema") != candidate.waiver_schema
        or claim.get("owner_launch_waiver_id") != candidate.waiver_id
        or claim.get("owner_waived_payload_sha256") != expected_waiver_sha
        or any(claim.get(key) != launch.get(key) for key in (
            "owner_launch_authority_mode", "owner_launch_waiver_schema",
            "owner_launch_waiver_id", "owner_waived_payload_sha256",
        ))
    ):
        _fail("tilt-ladder exact owner waiver receipt changed")
    _client(api)
    _check_uploaded_source(launch["project_id"], claim, api)
    _write(read_path, {
        "candidate_id": candidate.candidate_id,
        "project_id": launch["project_id"],
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
        or backtest.get("name") != candidate.backtest_name
        or backtest.get("status") != "Completed."
    ):
        _fail("tilt-ladder result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or tuple(sorted(
        key for key in statistics
        if type(key) is str and key.startswith("ARV2_SIX_GATE_ORDER_")
    )) != _CUSTOM_NAMES:
        _fail("tilt-ladder custom statistic inventory changed")
    try:
        _meta_text, meta = cap90._statistic(statistics[base_runtime.META_STATISTIC_NAME])
        aggregate_text, aggregate = cap90._statistic(
            statistics[base_runtime.AGGREGATES_STATISTIC_NAME]
        )
    except (KeyError, cap90.Cap90QcSubmissionError):
        _fail("tilt-ladder custom statistics are not bounded canonical JSON")
    summary_schema = f"arv2-six-universe-order-tilt{plan.percent}-bridge-summary-v1"
    rank_rule_id = tilt40_projection.TILT40_RANK_RULE_ID
    if (
        set(meta) != cap90._META_FIELDS
        or set(aggregate) != cap90._BRIDGE_AGGREGATE_FIELDS | _TILT_FIELDS
        or meta.get("schema") != base_runtime.META_SCHEMA
        or meta.get("role") != candidate.role
        or meta.get("profile_id") != launch["profile_id"]
        or meta.get("profile_sha256") != candidate.profile_sha256
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("activation_manifest_sha256") != plan.activation_manifest_sha256
        or type(meta.get("package_id")) is not str
        or not _ID.fullmatch(meta["package_id"])
        or type(meta.get("symbol_resolution_id")) is not str
        or not _ID.fullmatch(meta["symbol_resolution_id"])
        or type(meta.get("symbol_resolution_sha256")) is not str
        or not _HEX.fullmatch(meta["symbol_resolution_sha256"])
        or meta.get("result_transport") != "two_bounded_custom_summary_statistics"
        or meta.get("aggregate_schema") != summary_schema
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
        or aggregate.get("schema") != summary_schema
        or aggregate.get("role") != candidate.role
        or aggregate.get("profile_id") != launch["profile_id"]
        or aggregate.get("profile_sha256") != candidate.profile_sha256
        or aggregate.get("matched_baseline_profile_sha256")
        != cap90._R182_BRIDGE_PROFILE_SHA256
        or aggregate.get("matched_baseline_target_path_sha256") != matched_path_sha
        or aggregate.get("tilt_rank_rule_id") != rank_rule_id
        or aggregate.get("maximum_stock_weight_change_fraction")
        != f"0.{plan.percent:02d}"
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
        _fail("tilt-ladder result lineage, digest, or safety flag changed")
    core = {key: value for key, value in aggregate.items() if key not in _TILT_FIELDS}
    try:
        selected = cap90._project_aggregate(core, bridge=True)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseTiltLadderSubmissionError(str(exc)) from None
    selected.update({key: aggregate[key] for key in _TILT_FIELDS})
    valid = aggregate["run_valid"] is True
    if valid:
        _write(_control_path(plan, "result-valid"), {
            "candidate_id": candidate.candidate_id, "attempt": 1,
            "run_valid": True, "aggregate_sha256": meta["aggregate_sha256"],
            "projection_sha256": candidate.projection_sha256,
            "profile_sha256": candidate.profile_sha256,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return {"meta": meta, "aggregates": selected, "run_valid": valid}


__all__ = (
    "SixUniverseTiltLadderSubmissionError", "TiltLadderQcPlan", "launch_a1",
    "poll_status", "preview", "read_aggregates_once", "render_owner_waiver_payload",
)
