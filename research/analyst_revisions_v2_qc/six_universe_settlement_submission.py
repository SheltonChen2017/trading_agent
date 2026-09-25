"""One-use private QC order launches for the separately versioned cash policy.

Only R191 (matched), R192 (80% revision tilt), and R193 (100% revision tilt)
are admitted. Import does no I/O. The exact source, project, owner waiver,
predecessor, and result are authenticated independently. A completed QC
status alone is not a result.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from research.quantconnect import QuantConnectClient

from . import accepted_risk_six_universe_order_qc_projection as base_projection
from . import accepted_risk_six_universe_order_qc_runtime as base_runtime
from . import accepted_risk_six_universe_order_settlement_qc_projection as settlement_projection
from . import accepted_risk_six_universe_order_tilt100_qc_projection as tilt100_projection
from . import six_universe_cap90_submission as cap90
from . import six_universe_tilt80_submission as prior


class SixUniverseSettlementSubmissionError(ValueError):
    """An exact research source, launch, or result invariant failed."""


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    project_name: str
    role: str
    variant: str
    projection_schema: str
    projection_sha256: str
    profile_sha256: str
    source_files_sha256: str
    source_count: int
    total_source_bytes: int
    summary_schema: str
    waiver_id: str

    @property
    def backtest_name(self) -> str:
        return (
            f"ARV2 {self.candidate_id}A1 six cap90 settlement 2021 2025 "
            f"{self.projection_sha256[:8]}"
        )


# Literal host pins independently check the projected source authority. A
# candidate's private project and waiver must not be inferred from QC output.
_CANDIDATES = {
    "R191": _Candidate(
        "R191", "113 ARV2 SIX CAP90 SETTLED MATCHED R191 2021 2025",
        "matched", "cap90_admission_settlement_v1",
        "arv2-six-universe-order-qc-projection-settlement-v1",
        "883fc448d6b5a3f7800921988a174995ad233e0c8eab5434f6b18874b189a5bb",
        "f650044a704a4a0522e4c95c065a3eda3d3de22e8c5425579e04155c88f5220c",
        "5bf0cdc32148d84105256da5c818c1d023ee996b27a014302fe7c250ad1f9f73",
        14, 397_120,
        "arv2-six-universe-order-admission-settlement-summary-v1",
        "ARV2-OWNER-2026-09-25-R191A1-MATCHED-SETTLEMENT-EXPLORATORY-SIGNATURE-WAIVER",
    ),
    "R192": _Candidate(
        "R192", "114 ARV2 SIX CAP90 SETTLED TILT80 R192 2021 2025",
        "matched_revision_tilt80", "cap90_matched_revision_tilt80_settlement_v1",
        "arv2-six-universe-order-qc-projection-settlement-v1",
        "8f5db5bf895a51683d9c7c2a4848c302aeac01284317ceaab9e22d9c9b3c3b09",
        "2c149ea159473f7976f10daa5ad74b0a3f8d0bf6992911e96a58b3a7a490f923",
        "023707c5709525247ac88384e5ea356655ef5501fb7f07e19b158642456224ae",
        16, 425_742,
        "arv2-six-universe-order-tilt80-settlement-summary-v1",
        "ARV2-OWNER-2026-09-25-R192A1-TILT80-SETTLEMENT-EXPLORATORY-SIGNATURE-WAIVER",
    ),
    "R193": _Candidate(
        "R193", "115 ARV2 SIX CAP90 SETTLED TILT100 R193 2021 2025",
        "matched_revision_tilt100", "cap90_matched_revision_tilt100_settlement_v1",
        "arv2-six-universe-order-qc-projection-tilt100-settlement-v1",
        "473163be0d2b9281c4c18a2a1565146536d93eab8226dcf5a90556cece77bfb9",
        "c938f20cbcfe2bc3b4d60728b9ec7c9a450a88e5ba3fd0fe43a4c90985abc243",
        "2489eb7102ab7d6dd3f555d2aae5bc2c46df6816bd0d3ad4b78be77238d68abb",
        16, 425_754,
        "arv2-six-universe-order-tilt100-settlement-summary-v1",
        "ARV2-OWNER-2026-09-25-R193A1-TILT100-SETTLEMENT-EXPLORATORY-SIGNATURE-WAIVER",
    ),
}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ORG = re.compile(r"[0-9a-f]{32}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_PREDECESSOR_TARGET_PATH_SHA256 = (
    "b825663b4dfdee835f1c118a49fdd49e0a8d37387b8045060d77b5b3bbdcadbc"
)
_CUSTOM_NAMES = tuple(sorted((
    base_runtime.META_STATISTIC_NAME, base_runtime.AGGREGATES_STATISTIC_NAME,
)))
_MATCHED_SETTLEMENT_PROFILE_SHA256 = (
    "f650044a704a4a0522e4c95c065a3eda3d3de22e8c5425579e04155c88f5220c"
)


def _manifest_digest(manifest: tuple | list) -> str:
    return hashlib.sha256(_canonical(tuple(
        (row[0], row[1], row[2]) for row in manifest
    ))).hexdigest()


@dataclass(frozen=True)
class SettlementQcPlan:
    candidate_id: str
    organization_id: str
    package_sha256: str
    activation_manifest_sha256: str
    control_directory: Path
    attempt: int = 1

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
    def profile_sha256(self) -> str:
        return _candidate(self).profile_sha256

    @property
    def projection_sha256(self) -> str:
        return _candidate(self).projection_sha256


def _fail(message: str):
    raise SixUniverseSettlementSubmissionError(message)


def _canonical(value: object) -> bytes:
    return cap90._canonical(value)


def _candidate(plan: SettlementQcPlan) -> _Candidate:
    if type(plan) is not SettlementQcPlan or type(plan.candidate_id) is not str:
        _fail("settlement plan type changed")
    candidate = _CANDIDATES.get(plan.candidate_id)
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
        _fail("settlement plan changed from its exact A1 identity")
    return candidate


def _post(api: QuantConnectClient, endpoint: str, payload: dict) -> dict:
    try:
        return cap90._post(api, endpoint, payload)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None


def _client(api: QuantConnectClient) -> None:
    try:
        cap90._client(api)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None


def _control_path(plan: SettlementQcPlan, name: str) -> Path:
    candidate = _candidate(plan)
    if name not in {"claim", "launch", "terminal", "result-read-claim", "result-valid"}:
        _fail("settlement control name is not allowlisted")
    root = plan.control_directory
    try:
        root.mkdir(mode=0o700)
        info = root.stat(follow_symlinks=False)
    except FileExistsError:
        info = root.stat(follow_symlinks=False)
    except OSError:
        _fail("settlement control directory is unavailable")
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        _fail("settlement control directory is not private")
    return root / f"{candidate.candidate_id}-A1-{name}.json"


def _read(path: Path) -> dict:
    try:
        return cap90._read_control(path)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None


def _write(path: Path, value: dict) -> None:
    try:
        cap90._write_once(path, value)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None


def _source_manifest(projection: object, candidate: _Candidate) -> tuple:
    if (
        type(projection.source_files) is not tuple
        or len(projection.source_files) != candidate.source_count
        or projection.total_source_byte_count != candidate.total_source_bytes
    ):
        _fail("settlement source count or total bytes changed")
    paths = []
    manifest = []
    for item in projection.source_files:
        if (
            type(item.project_path) is not str
            or not cap90._PATH.fullmatch(item.project_path)
            or ".." in Path(item.project_path).parts
            or type(item.source_bytes) is not bytes
            or not 0 < len(item.source_bytes) <= 64_000
            or item.byte_count != len(item.source_bytes)
            or hashlib.sha256(item.source_bytes).hexdigest() != item.content_sha256
        ):
            _fail("settlement projected file identity changed")
        try:
            item.source_bytes.decode("ascii")
        except UnicodeError:
            _fail("settlement projected source is not ASCII")
        paths.append(item.project_path)
        manifest.append((item.project_path, item.content_sha256, item.byte_count))
    if (
        tuple(paths) != tuple(sorted(paths))
        or len(set(paths)) != candidate.source_count
        or "main.py" not in paths
        or sum(row[2] for row in manifest) != candidate.total_source_bytes
        or candidate.total_source_bytes + base_projection.MINIMUM_REVIEW_MARGIN_BYTES
        > base_projection.MAXIMUM_TOTAL_SOURCE_BYTES
        or _manifest_digest(manifest) != candidate.source_files_sha256
    ):
        _fail("settlement source closure or manifest changed")
    return tuple(manifest)


def preview(plan: SettlementQcPlan, projection: object) -> dict:
    """Authenticate the exact source before any QC call or attempt claim."""
    candidate = _candidate(plan)
    if (
        type(projection) is not base_projection.AcceptedRiskSixUniverseOrderQcProjection
        or projection.schema != candidate.projection_schema
        or projection.role != candidate.role
        or projection.variant != candidate.variant
        or projection.projection_sha256 != candidate.projection_sha256
        or projection.profile_sha256 != candidate.profile_sha256
        or projection.package_sha256 != plan.package_sha256
        or projection.activation_manifest_sha256 != plan.activation_manifest_sha256
    ):
        _fail("settlement projection, profile, or package changed")
    if candidate.candidate_id == "R193":
        try:
            profile = tilt100_projection.require_tilt100_profile()
        except tilt100_projection.SixUniverseTilt100QcProjectionError as exc:
            raise SixUniverseSettlementSubmissionError(str(exc)) from None
        projection_id_prefix = tilt100_projection.PROJECTION_ID_PREFIX
    else:
        try:
            profile = settlement_projection.require_settlement_profile(candidate.candidate_id)
        except settlement_projection.SixUniverseSettlementQcProjectionError as exc:
            raise SixUniverseSettlementSubmissionError(str(exc)) from None
        projection_id_prefix = "arv2-six-universe-order-settlement-qc-projection-"
    if (
        profile.get("profile_id") != projection.profile_id
        or profile.get("profile_sha256") != candidate.profile_sha256
        or profile.get("transient_pending_sell_cash_deficit_allowed") is not True
        or profile.get("settled_cash_nonnegative_required") is not True
        or profile.get("event_cash_policy_id")
        != settlement_projection.SETTLEMENT_POLICY_ID
        or "realized_borrowing_allowed" in profile
    ):
        _fail("settlement profile cash policy changed")
    manifest = _source_manifest(projection, candidate)
    semantic = {key: value for key, value in projection.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    if (
        digest != candidate.projection_sha256
        or projection.projection_id != projection_id_prefix + digest[:24]
    ):
        _fail("settlement projection is not self-authenticating")
    return {
        "candidate_id": candidate.candidate_id, "attempt": 1,
        "role": candidate.role, "projection_sha256": candidate.projection_sha256,
        "profile_id": projection.profile_id,
        "profile_sha256": candidate.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "source_files": manifest,
    }


def _require_valid_predecessor(plan: SettlementQcPlan) -> str:
    try:
        target_path_sha = prior._require_valid_predecessors(plan)
    except prior.SixUniverseTilt80SubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None
    if target_path_sha != _PREDECESSOR_TARGET_PATH_SHA256:
        _fail("settlement R182 target path changed")
    return target_path_sha


def _waiver_payload(plan: SettlementQcPlan, identity: dict, target_path: str) -> bytes:
    candidate = _candidate(plan)
    if target_path != _PREDECESSOR_TARGET_PATH_SHA256:
        _fail("settlement predecessor target path changed")
    return _canonical({
        "schema": f"arv2-six-universe-{candidate.candidate_id.lower()}-settlement-waiver-v1",
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": candidate.waiver_id,
        "action": "one_private_exploratory_order_backtest_launch",
        "candidate_id": candidate.candidate_id, "attempt": 1,
        "role": candidate.role,
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
        "matched_baseline_target_path_sha256": target_path,
        "source_files_sha256": candidate.source_files_sha256,
        "mutating_endpoint_budget": {
            "projects/create": 1, "files/delete": 1,
            "files/create": candidate.source_count, "files/update": 1,
            "compile/create": 1, "backtests/create": 1,
        },
        "maximum_backtest_submissions": 1,
        "aggregate_only_result_read_authorized": True,
        "maximum_result_reads": 1,
        "raw_provider_rows_authorized": False,
        "raw_logs_orders_charts_authorized": False,
        "paper_live_deployment_funded_trading_authorized": False,
    })


def render_owner_waiver_payload(plan: SettlementQcPlan, projection: object) -> bytes:
    identity = preview(plan, projection)
    return _waiver_payload(plan, identity, _require_valid_predecessor(plan))


def _check_uploaded_source(project_id: int, identity: dict,
                           api: QuantConnectClient) -> None:
    files = _post(api, "files/read", {"projectId": project_id}).get("files")
    expected = identity["source_files"]
    if type(files) is not list or len(files) != len(expected):
        _fail("settlement uploaded source inventory changed")
    observed = {}
    for item in files:
        if (
            type(item) is not dict or item.get("projectId") != project_id
            or type(item.get("name")) is not str
            or type(item.get("content")) is not str
            or item["name"] in observed
        ):
            _fail("settlement uploaded file identity changed")
        observed[item["name"]] = item["content"]
    if set(observed) != {row[0] for row in expected}:
        _fail("settlement uploaded source paths changed")
    for path, digest, size in expected:
        try:
            raw = observed[path].encode("ascii")
        except UnicodeError:
            _fail("settlement uploaded source is not ASCII")
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            _fail("settlement uploaded source bytes changed")


def launch_a1(
    plan: SettlementQcPlan, projection: object, api: QuantConnectClient, *,
    owner_waiver_id: str,
) -> dict:
    """Claim one A1, create a fresh private project, and submit exact source."""
    candidate = _candidate(plan)
    identity = preview(plan, projection)
    target_path = _require_valid_predecessor(plan)
    if type(owner_waiver_id) is not str or owner_waiver_id != candidate.waiver_id:
        _fail("settlement owner waiver does not cover this candidate")
    authority = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": (
            f"arv2-six-universe-{candidate.candidate_id.lower()}-settlement-waiver-v1"
        ),
        "owner_launch_waiver_id": candidate.waiver_id,
        "owner_waived_payload_sha256": hashlib.sha256(
            _waiver_payload(plan, identity, target_path)
        ).hexdigest(),
    }
    claim_path = _control_path(plan, "claim")
    if claim_path.exists():
        _fail("settlement A1 attempt was already claimed")
    _client(api)
    _post(api, "authenticate", {})
    projects = _post(api, "projects/read", {}).get("projects")
    if type(projects) is not list or any(
        type(item) is not dict or item.get("name") == candidate.project_name
        for item in projects
    ):
        _fail("settlement project name is not fresh")
    _write(claim_path, {
        **identity, **authority,
        "matched_baseline_target_path_sha256": target_path,
    })
    created = _post(api, "projects/create", {
        "name": candidate.project_name, "language": "Py",
        "organizationId": plan.organization_id,
    }).get("projects")
    if type(created) is not list or len(created) != 1 or type(created[0]) is not dict:
        _fail("settlement created project response changed")
    project_id = created[0].get("projectId")
    if type(project_id) is not int or project_id <= 0:
        _fail("settlement created project ID changed")
    verified = _post(api, "projects/read", {"projectId": project_id}).get("projects")
    if type(verified) is not list or len(verified) != 1 or type(verified[0]) is not dict:
        _fail("settlement project readback changed")
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
        or any(type(item) is not dict or item.get("owner") is not True
               for item in collaborators)
    ):
        _fail("settlement project is not private and idle")
    initial = _post(api, "files/read", {"projectId": project_id}).get("files")
    if type(initial) is not list or any(
        type(item) is not dict or item.get("name") not in cap90._DEFAULT_FILES
        for item in initial
    ):
        _fail("settlement default file inventory changed")
    initial_names = [item["name"] for item in initial]
    if len(initial_names) != len(set(initial_names)):
        _fail("settlement default source paths duplicated")
    if "research.ipynb" in initial_names:
        _post(api, "files/delete", {
            "projectId": project_id, "name": "research.ipynb",
        })
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
        _fail("settlement compile identity changed")
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
            _fail("settlement compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("settlement compile poll exhausted; A1 remains spent")
    if state["state"] == "BuildError":
        _write(_control_path(plan, "terminal"), {
            "candidate_id": candidate.candidate_id, "status": "BuildError",
            "project_id": project_id, "compile_id": compile_id,
        })
        _fail("settlement compile failed; A1 was consumed")
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
        _fail("settlement backtest launch identity changed")
    receipt = {
        **{key: value for key, value in identity.items() if key != "source_files"},
        **authority,
        "matched_baseline_target_path_sha256": target_path,
        "project_id": project_id, "project_name": candidate.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": candidate.backtest_name,
    }
    _write(_control_path(plan, "launch"), receipt)
    return receipt


def _match_launch(plan: SettlementQcPlan, launch: dict) -> _Candidate:
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
        or type(launch.get("project_id")) is not int
        or launch["project_id"] <= 0
        or type(launch.get("backtest_id")) is not str
        or not _ID.fullmatch(launch["backtest_id"])
    ):
        _fail("settlement launch receipt differs from exact plan")
    return candidate


def poll_status(
    plan: SettlementQcPlan, launch: dict, api: QuantConnectClient,
) -> str:
    """Read only terminal status, never statistics, logs, charts, or orders."""
    candidate = _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("settlement launch receipt changed")
    terminal_path = _control_path(plan, "terminal")
    if terminal_path.exists():
        return _read(terminal_path)["status"]
    _client(api)
    listing = _post(api, "backtests/list", {
        "projectId": launch["project_id"], "includeStatistics": False,
    })
    rows = listing.get("backtests")
    if type(rows) is not list or listing.get("count", len(rows)) != len(rows):
        _fail("settlement backtest status inventory changed")
    matched = [item for item in rows if type(item) is dict
               and item.get("backtestId") == launch["backtest_id"]]
    if len(matched) != 1:
        _fail("settlement exact backtest status is absent")
    row = matched[0]
    status = row.get("status")
    if (
        row.get("name") != candidate.backtest_name
        or ("projectId" in row and row["projectId"] != launch["project_id"])
        or status not in {
            "In Queue...", "In Progress...", "Completed.", "Runtime Error",
        }
    ):
        _fail("settlement backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        _write(terminal_path, {
            "candidate_id": candidate.candidate_id, "status": status,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        })
    return status


_SETTLEMENT_FIELDS = frozenset({
    "admission_leverage", "target_gross_exposure", "minimum_end_day_cash",
    "daily_cash_nonnegative", "order_event_cash_observation_count",
    "minimum_observed_order_event_cash", "transient_negative_order_event_count",
    "unexplained_negative_order_event_count",
    "negative_cash_requires_pending_sell_moo", "settled_cash_nonnegative",
    "cash_observation_granularity", "end_day_gross_at_most_one",
    "target_tracking_valid", "maximum_mean_target_weight_l1_error",
    "maximum_single_target_weight_l1_error",
})
_TILT_FIELDS = frozenset({
    "matched_baseline_profile_sha256", "matched_baseline_target_path_sha256",
    "tilt_rank_rule_id", "maximum_stock_weight_change_fraction",
})
_TILT_FRACTIONS = {"R192": "0.80", "R193": "1.00"}


def _exact_result_claim(
    plan: SettlementQcPlan, launch: dict, candidate: _Candidate,
) -> dict:
    """Rebind source, predecessor and waiver before consuming the one read."""
    claim = _read(_control_path(plan, "claim"))
    source_files = claim.get("source_files")
    target_path = _require_valid_predecessor(plan)
    if (
        claim.get("candidate_id") != candidate.candidate_id
        or claim.get("attempt") != 1
        or claim.get("role") != candidate.role
        or type(source_files) is not list
        or len(source_files) != candidate.source_count
        or any(
            type(row) is not list or len(row) != 3
            or type(row[0]) is not str or type(row[1]) is not str
            or type(row[2]) is not int or row[2] <= 0
            for row in source_files
        )
        or _manifest_digest(source_files) != candidate.source_files_sha256
        or claim.get("projection_sha256") != candidate.projection_sha256
        or claim.get("profile_sha256") != candidate.profile_sha256
        or claim.get("package_sha256") != plan.package_sha256
        or claim.get("activation_manifest_sha256") != plan.activation_manifest_sha256
        or claim.get("matched_baseline_target_path_sha256") != target_path
        or any(claim.get(key) != launch.get(key) for key in (
            "candidate_id", "attempt", "role", "projection_sha256",
            "profile_id", "profile_sha256", "package_sha256",
            "activation_manifest_sha256", "matched_baseline_target_path_sha256",
        ))
    ):
        _fail("settlement source claim or predecessor changed")
    waiver_sha = hashlib.sha256(
        _waiver_payload(plan, claim, target_path)
    ).hexdigest()
    if (
        claim.get("owner_launch_authority_mode")
        != "exact_exploratory_signature_waiver"
        or claim.get("owner_launch_waiver_schema") != (
            f"arv2-six-universe-{candidate.candidate_id.lower()}-settlement-waiver-v1"
        )
        or claim.get("owner_launch_waiver_id") != candidate.waiver_id
        or claim.get("owner_waived_payload_sha256") != waiver_sha
        or any(claim.get(key) != launch.get(key) for key in (
            "owner_launch_authority_mode", "owner_launch_waiver_schema",
            "owner_launch_waiver_id", "owner_waived_payload_sha256",
        ))
    ):
        _fail("settlement owner waiver receipt changed")
    return claim


def _settlement_aggregate(
    aggregate: dict, candidate: _Candidate, *, matched_target_path: str,
) -> dict:
    """Retain only an exact, internally consistent new-policy aggregate."""
    tilt_fields = (_TILT_FIELDS if candidate.candidate_id in _TILT_FRACTIONS
                   else frozenset())
    if (
        type(aggregate) is not dict
        or set(aggregate) != cap90._AGGREGATE_FIELDS | _SETTLEMENT_FIELDS | tilt_fields
        or aggregate.get("schema") != candidate.summary_schema
        or aggregate.get("role") != candidate.role
        or aggregate.get("admission_leverage") != "2"
        or aggregate.get("target_gross_exposure") != "0.98"
        or aggregate.get("maximum_mean_target_weight_l1_error") != "0.02"
        or aggregate.get("maximum_single_target_weight_l1_error") != "0.05"
        or aggregate.get("cash_observation_granularity") != (
            "daily_close_and_post_order_event_not_continuous_intraday"
        )
        or aggregate.get("daily_cash_nonnegative") is not True
        or aggregate.get("settled_cash_nonnegative") is not True
        or aggregate.get("negative_cash_requires_pending_sell_moo") is not True
        or aggregate.get("unexplained_negative_order_event_count") != 0
        or type(aggregate.get("unexplained_negative_order_event_count")) is not int
    ):
        _fail("settlement schema, role, or signed-cash policy changed")
    event_count = aggregate["order_event_cash_observation_count"]
    transient_count = aggregate["transient_negative_order_event_count"]
    event_minimum = aggregate["minimum_observed_order_event_cash"]
    daily_minimum = aggregate["minimum_end_day_cash"]
    execution = aggregate.get("execution")
    if (
        type(event_count) is not int or event_count < 0
        or type(transient_count) is not int or not 0 <= transient_count <= event_count
        or not cap90._finite_decimal(daily_minimum)
        or Decimal(daily_minimum) < 0
        or (event_count == 0 and event_minimum is not None)
        or (event_count > 0 and not cap90._finite_decimal(event_minimum))
        or (event_count > 0 and (
            (transient_count > 0) is not (Decimal(event_minimum) < 0)
        ))
        or type(execution) is not dict
        or not cap90._finite_decimal(execution.get("mean_target_weight_l1_error"))
        or not cap90._finite_decimal(execution.get("maximum_target_weight_l1_error"))
        or not cap90._finite_decimal(aggregate.get("maximum_gross_exposure"))
    ):
        _fail("settlement signed event cash, daily cash, or tracking changed")
    mean_error = Decimal(execution["mean_target_weight_l1_error"])
    maximum_error = Decimal(execution["maximum_target_weight_l1_error"])
    gross = Decimal(aggregate["maximum_gross_exposure"])
    if (
        mean_error < 0 or maximum_error < 0 or gross < 0
        or aggregate.get("end_day_gross_at_most_one") is not (gross <= 1)
        or aggregate.get("target_tracking_valid") is not (
            mean_error <= Decimal("0.02")
            and maximum_error <= Decimal("0.05")
        )
        or type(aggregate.get("run_valid")) is not bool
        or type(execution.get("run_valid")) is not bool
        or (aggregate["run_valid"] and (
            execution["run_valid"] is not True
            or event_count == 0
            or aggregate["end_day_gross_at_most_one"] is not True
            or aggregate["target_tracking_valid"] is not True
            or execution.get("submitted_rebalance_count") != base_runtime.EXPECTED_DECISION_COUNT
            or execution.get("completed_rebalance_count") != base_runtime.EXPECTED_DECISION_COUNT
            or execution.get("submitted_order_count")
            != execution.get("filled_order_count_sum")
            or execution.get("invalid_order_count_sum") != 0
            or execution.get("canceled_order_count_sum") != 0
            or execution.get("execution_failure") is not False
        ))
    ):
        _fail("settlement order, exposure, or tracking validity changed")
    if candidate.candidate_id in _TILT_FRACTIONS and (
        aggregate.get("matched_baseline_profile_sha256")
        != _MATCHED_SETTLEMENT_PROFILE_SHA256
        or aggregate.get("matched_baseline_target_path_sha256")
        != matched_target_path
        or aggregate.get("maximum_stock_weight_change_fraction")
        != _TILT_FRACTIONS[candidate.candidate_id]
    ):
        _fail("settlement tilt or matched target binding changed")
    base = {key: aggregate[key] for key in cap90._AGGREGATE_FIELDS}
    try:
        selected = cap90._project_aggregate(base, bridge=False)
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None
    selected.update({key: aggregate[key] for key in _SETTLEMENT_FIELDS | tilt_fields})
    selected["execution"].update({
        "mean_target_weight_l1_error": execution["mean_target_weight_l1_error"],
        "maximum_target_weight_l1_error": execution["maximum_target_weight_l1_error"],
    })
    return selected


def read_aggregates_once(
    plan: SettlementQcPlan, launch: dict, api: QuantConnectClient,
) -> dict:
    """Consume one bounded custom-statistic read after exact completion."""
    candidate = _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("settlement launch receipt changed")
    if _read(_control_path(plan, "terminal")) != {
        "candidate_id": candidate.candidate_id, "status": "Completed.",
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    }:
        _fail("settlement exact run did not complete")
    read_path = _control_path(plan, "result-read-claim")
    if read_path.exists():
        _fail("settlement result read was already claimed")
    claim = _exact_result_claim(plan, launch, candidate)
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
        _fail("settlement result identity changed")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict or tuple(sorted(
        key for key in statistics
        if type(key) is str and key.startswith("ARV2_SIX_GATE_ORDER_")
    )) != _CUSTOM_NAMES:
        _fail("settlement custom statistic inventory changed")
    try:
        _meta_text, meta = cap90._statistic(statistics[base_runtime.META_STATISTIC_NAME])
        aggregate_text, aggregate = cap90._statistic(
            statistics[base_runtime.AGGREGATES_STATISTIC_NAME]
        )
    except (KeyError, cap90.Cap90QcSubmissionError):
        _fail("settlement custom statistics are not bounded canonical JSON")
    if (
        set(meta) != cap90._META_FIELDS
        or meta.get("schema") != base_runtime.META_SCHEMA
        or meta.get("role") != candidate.role
        or meta.get("profile_id") != launch["profile_id"]
        or meta.get("profile_sha256") != candidate.profile_sha256
        or meta.get("package_sha256") != plan.package_sha256
        or meta.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or type(meta.get("package_id")) is not str
        or not _ID.fullmatch(meta["package_id"])
        or type(meta.get("symbol_resolution_id")) is not str
        or not _ID.fullmatch(meta["symbol_resolution_id"])
        or type(meta.get("symbol_resolution_sha256")) is not str
        or not _HEX.fullmatch(meta["symbol_resolution_sha256"])
        or meta.get("result_transport")
        != "two_bounded_custom_summary_statistics"
        or meta.get("aggregate_schema") != candidate.summary_schema
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
        or aggregate.get("profile_id") != launch["profile_id"]
        or aggregate.get("profile_sha256") != candidate.profile_sha256
        or aggregate.get("backtest_only") is not True
        or aggregate.get("preliminary") is not True
        or aggregate.get("formal") is not False
        or any(aggregate.get(key) is not False for key in (
            "live_orders", "paper_orders", "funded_orders", "deployment", "trading",
        ))
    ):
        _fail("settlement result lineage, digest, or safety flag changed")
    selected = _settlement_aggregate(
        aggregate, candidate,
        matched_target_path=_PREDECESSOR_TARGET_PATH_SHA256,
    )
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
    "SettlementQcPlan", "SixUniverseSettlementSubmissionError", "launch_a1",
    "poll_status", "preview", "read_aggregates_once", "render_owner_waiver_payload",
)
