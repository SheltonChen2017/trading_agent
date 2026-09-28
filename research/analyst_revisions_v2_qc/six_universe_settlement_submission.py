"""One-use private QC order launches for the separately versioned cash policy.

R191 (matched), R192 (80% revision tilt), R193 (100% revision tilt), and the
separately pinned R194 positive-residual correction are admitted. R194 is a
one-time fourth look in the R193 lineage, not a reset of its attempt budget.
R195-R202 are separately pinned 100/120/140/160/180/200/250/300% exploratory launches.
Each authenticates its own matched target path; only a path match to a valid
R195 receipt permits a later candidate comparison.
Import does no I/O. The exact source, project, owner waiver,
predecessor, and result are authenticated independently. A completed QC
status alone is not a result.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from research.quantconnect import QuantConnectClient

from . import accepted_risk_six_universe_order_qc_projection as base_projection
from . import accepted_risk_six_universe_order_qc_runtime as base_runtime
from . import accepted_risk_six_universe_order_settlement_qc_projection as settlement_projection
from . import accepted_risk_six_universe_order_tilt100_qc_projection as tilt100_projection
from . import accepted_risk_six_universe_order_tilt100_floor_qc_projection as floor_projection
from . import accepted_risk_six_universe_order_tilt_ladder_floor_qc_projection as ladder_projection
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
        window = "202508 NOW" if self.candidate_id in _RECENT_PERCENTS else "2021 2025"
        return (
            f"ARV2 {self.candidate_id}A1 six cap90 settlement {window} "
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
    "R194": _Candidate(
        "R194", "116 ARV2 SIX CAP90 SETTLED TILT100 FLOOR R194 2021 2025",
        floor_projection.TILT_ROLE, floor_projection.TILT_VARIANT,
        floor_projection.PROJECTION_SCHEMA,
        "c10b1aa8c6d56104ec6fcdc134a4a335ae648df9be67a75894cf79090b33dd85",
        "1f338baac6cad9ea0e95661d8320711013435e24d20a2d7ee67496194a430053",
        "2e51cd6547908ac2c3adbae5430fdb7ce4e2af8e724002281931c59d58b88d5c",
        16, 425_919,
        floor_projection.SUMMARY_SCHEMA,
        "ARV2-OWNER-2026-09-25-R193-LINEAGE-LOOK4-R194-ONE-TIME-EXCEPTION",
    ),
    "R195": _Candidate(
        "R195", "117 ARV2 SIX CAP90 SETTLED TILT100 GUARD R195 2021 2025",
        ladder_projection.TILT_ROLES[100], ladder_projection.TILT_VARIANTS[100],
        ladder_projection.PROJECTION_SCHEMAS[100],
        "c20e2c13ef477e4c1619cb93aafb4fef58c2a36c95f5a514c62d015f5722e28d",
        "ecdc210a6f65ea1ee8e2163e4dc3debaf8b0c0996a457c57299dbed1c4198561",
        "75a3cfd8091e6311e34c0295e787969a5ba637fc2da74f9e83c70fd7700fdef3",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[100],
        "ARV2-OWNER-2026-09-25-R195A1-TILT100-GUARD-EXPLORATORY",
    ),
    "R196": _Candidate(
        "R196", "118 ARV2 SIX CAP90 SETTLED TILT120 GUARD R196 2021 2025",
        ladder_projection.TILT_ROLES[120], ladder_projection.TILT_VARIANTS[120],
        ladder_projection.PROJECTION_SCHEMAS[120],
        "f8489764d1925f93ecd13092d5ef0d916f681385a12dc817f02115f66328f82e",
        "cf9932e48e2f282713101d8d38dec2e702b08a7796ae8ccb503abff7f32234c1",
        "1b933d0f925b3103a875e9960c24741856a33b50e0b3c5c1675bfed07d76c051",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[120],
        "ARV2-OWNER-2026-09-25-R196A1-TILT120-GUARD-EXPLORATORY",
    ),
    "R197": _Candidate(
        "R197", "119 ARV2 SIX CAP90 SETTLED TILT140 GUARD R197 2021 2025",
        ladder_projection.TILT_ROLES[140], ladder_projection.TILT_VARIANTS[140],
        ladder_projection.PROJECTION_SCHEMAS[140],
        "c3edcd8bae80446fd564e4d21a1a8ff3c8a35ee68af914b13de2a344ab596576",
        "83893aca4ab0dd0b0a98eb39f51b8a8c2f77ef114a1cf231acd9214437c3287f",
        "2456ee4d5089a4d9cd7cdd87068f0d1f5897ce87a6ffb1b4dfd0938ec0bf6082",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[140],
        "ARV2-OWNER-2026-09-25-R197A1-TILT140-GUARD-EXPLORATORY",
    ),
    "R198": _Candidate(
        "R198", "120 ARV2 SIX CAP90 SETTLED TILT160 GUARD R198 2021 2025",
        ladder_projection.TILT_ROLES[160], ladder_projection.TILT_VARIANTS[160],
        ladder_projection.PROJECTION_SCHEMAS[160],
        "97fdd9a4332ae2d973399535c2687153e08a81ccd2eb1e4a89daf4270c687a9f",
        "7b4dac4771d1cfaf5851cb8d4c31448d01f8408baa652857292755fe88776a87",
        "514230dd7bde96f347d2d6eae390d2c7b4fb09403c1ca7cf687f6da228eb383f",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[160],
        "ARV2-OWNER-2026-09-25-R198A1-TILT160-GUARD-EXPLORATORY",
    ),
    "R199": _Candidate(
        "R199", "121 ARV2 SIX CAP90 SETTLED TILT180 GUARD R199 2021 2025",
        ladder_projection.TILT_ROLES[180], ladder_projection.TILT_VARIANTS[180],
        ladder_projection.PROJECTION_SCHEMAS[180],
        "773787eac1cce21d27be7dd5256b917c453c3f8474a0a0d24e8b7ef9dd86d09d",
        "46d6b61812c48d2d5797ac636e5919e160a6adca6e06005f2f31c596cdc7c778",
        "0cc2299ac2062366046da0a027f88946fe684bcc87f27974ceab174a1da0035f",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[180],
        "ARV2-OWNER-2026-09-25-R199A1-TILT180-GUARD-EXPLORATORY",
    ),
    "R200": _Candidate(
        "R200", "122 ARV2 SIX CAP90 SETTLED TILT200 GUARD R200 2021 2025",
        ladder_projection.TILT_ROLES[200], ladder_projection.TILT_VARIANTS[200],
        ladder_projection.PROJECTION_SCHEMAS[200],
        "e8cc677ad751362fe702949ab52daa24ec89ade8bc6b303779a815543ef213cb",
        "3b6acc8e91cd674d267bde3985b8fc123a5c2fbc809c87acfb9c74b2c3ec215c",
        "c2bb27d8a851d365d3ab45813e9e62aa3e63fc110cd69cac05b8791585249745",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[200],
        "ARV2-OWNER-2026-09-25-R200A1-TILT200-GUARD-EXPLORATORY",
    ),
    "R201": _Candidate(
        "R201", "123 ARV2 SIX CAP90 SETTLED TILT250 GUARD R201 2021 2025",
        ladder_projection.TILT_ROLES[250], ladder_projection.TILT_VARIANTS[250],
        ladder_projection.PROJECTION_SCHEMAS[250],
        "09af59032015e04b8e7a97a0f54f90a240cc87b38ed793700bf58bcedca98780",
        "cd38f3589131bbec453aee57b726dd09ca4f7b77441db3fe2673bafa104d6ca6",
        "f20e12994b333178342031700011ce0c86421db550dfeb154b5dd9a794632788",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[250],
        "ARV2-OWNER-2026-09-25-R201A1-TILT250-GUARD-EXPLORATORY",
    ),
    "R202": _Candidate(
        "R202", "124 ARV2 SIX CAP90 SETTLED TILT300 GUARD R202 2021 2025",
        ladder_projection.TILT_ROLES[300], ladder_projection.TILT_VARIANTS[300],
        ladder_projection.PROJECTION_SCHEMAS[300],
        "5eeaa095fe57f267cf8093525c01646717c3c77f235acbaf46d185224fead287",
        "5c023ec203cd14753f1dcb049d1fbb85da5078f6b16b85fe03b78a22336f7714",
        "46c85fbbe6fb4288e0ff73d8f48c8a52e3ef0e0328fbf3aefe725e5fad39a392",
        16, 425_975,
        ladder_projection.SUMMARY_SCHEMAS[300],
        "ARV2-OWNER-2026-09-25-R202A1-TILT300-GUARD-EXPLORATORY",
    ),
}
_LADDER_PERCENTS = {
    "R195": 100, "R196": 120, "R197": 140,
    "R198": 160, "R199": 180, "R200": 200,
    "R201": 250, "R202": 300,
}
_LATER_LADDER_CANDIDATES = frozenset(_LADDER_PERCENTS) - {"R195"}
_RECENT_PERCENTS = {
    "R203": 100, "R204": 120, "R205": 140,
    "R206": 160, "R207": 180, "R208": 200,
}
_ALL_GUARDED_IDS = frozenset(_LADDER_PERCENTS) | frozenset(_RECENT_PERCENTS)
_RECENT_GEOMETRY = ("2025-08-01", "2026-09-25", 290, 61)
_R195_A2_PROJECT_ID = 36963958
_R195_A2_WAIVER_ID = (
    "ARV2-OWNER-2026-09-25-R195A2-TILT100-GUARD-RECOVERY-EXPLORATORY"
)
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
        candidate = _candidate(self)
        if self.candidate_id in {"R195", "R203"} and self.attempt == 2:
            return candidate.backtest_name.replace(
                self.candidate_id + "A1", self.candidate_id + "A2", 1)
        return candidate.backtest_name

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
    if plan.candidate_id in _RECENT_PERCENTS:
        recent = _recent_adapter()
        recent.require_package_binding(plan)
        candidate = recent.TRUSTED_CANDIDATES.get(plan.candidate_id)
    if candidate is None or (
        type(plan.attempt) is not int
        or plan.attempt not in ((1, 2) if plan.candidate_id in {"R195", "R203"} else (1,))
        or type(plan.organization_id) is not str
        or not _ORG.fullmatch(plan.organization_id)
        or type(plan.package_sha256) is not str
        or not _HEX.fullmatch(plan.package_sha256)
        or type(plan.activation_manifest_sha256) is not str
        or not _HEX.fullmatch(plan.activation_manifest_sha256)
        or not isinstance(plan.control_directory, Path)
        or not plan.control_directory.is_absolute()
    ):
        _fail("settlement plan changed from its exact attempt identity")
    return candidate


def _recent_adapter():
    # The new adapter owns independent literal pins; loading it never changes
    # the historical registry or substitutes a short window into old globals.
    from . import six_universe_recent_settlement_submission
    return six_universe_recent_settlement_submission


def _matched_profile_sha256(candidate: _Candidate) -> str:
    if candidate.candidate_id in _RECENT_PERCENTS:
        return _recent_adapter().MATCHED_BASELINE_PROFILE_SHA256
    return _MATCHED_SETTLEMENT_PROFILE_SHA256


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
    if name not in {"claim", "launch", "terminal", "result-read-claim", "result-valid"} and not (
        candidate.candidate_id == "R203"
        and name in {"inputs-upload-claim", "inputs-upload-valid", "visibility-evidence"}
    ):
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
    return root / f"{candidate.candidate_id}-A{plan.attempt}-{name}.json"


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
    if candidate.candidate_id in _RECENT_PERCENTS:
        percent = _RECENT_PERCENTS[candidate.candidate_id]
        recent = _recent_adapter()
        profile = recent.require_profile(percent)
        projection_id_prefix = recent.PROJECTION_ID_PREFIXES[percent]
        if (
            profile.get("role") != candidate.role
            or profile.get("maximum_stock_weight_change_fraction")
            != _TILT_FRACTIONS[candidate.candidate_id]
            or profile.get("minimum_stock_and_sleeve_residual_weight") != "1e-30"
            or profile.get("matched_baseline_profile_sha256")
            != _matched_profile_sha256(candidate)
            or profile.get("evaluation_start_session") != _RECENT_GEOMETRY[0]
            or profile.get("evaluation_end_session") != _RECENT_GEOMETRY[1]
            or profile.get("evaluation_session_count") != _RECENT_GEOMETRY[2]
            or profile.get("decision_count") != _RECENT_GEOMETRY[3]
        ):
            _fail("settlement recent-window rule, geometry, or matched profile changed")
    elif candidate.candidate_id in _LADDER_PERCENTS:
        percent = _LADDER_PERCENTS[candidate.candidate_id]
        try:
            profile = ladder_projection.require_tilt_floor_profile(percent)
        except ladder_projection.SixUniverseTiltLadderFloorQcProjectionError as exc:
            raise SixUniverseSettlementSubmissionError(str(exc)) from None
        projection_id_prefix = ladder_projection.PROJECTION_ID_PREFIXES[percent]
        if (
            profile.get("role") != candidate.role
            or profile.get("maximum_stock_weight_change_fraction")
            != _TILT_FRACTIONS[candidate.candidate_id]
            or profile.get("minimum_stock_and_sleeve_residual_weight") != "1e-30"
            or profile.get("matched_baseline_profile_sha256")
            != _MATCHED_SETTLEMENT_PROFILE_SHA256
        ):
            _fail("settlement guarded tilt rule or matched profile changed")
    elif candidate.candidate_id == "R194":
        try:
            profile = floor_projection.require_tilt100_floor_profile()
        except floor_projection.SixUniverseTilt100FloorQcProjectionError as exc:
            raise SixUniverseSettlementSubmissionError(str(exc)) from None
        projection_id_prefix = floor_projection.PROJECTION_ID_PREFIX
        if (
            profile.get("role") != floor_projection.TILT_ROLE
            or profile.get("maximum_stock_weight_change_fraction") != "1.00"
            or profile.get("minimum_stock_residual_weight") != "1e-30"
        ):
            _fail("R194 positive-residual tilt rule changed")
    elif candidate.candidate_id == "R193":
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
    identity = {
        "candidate_id": candidate.candidate_id, "attempt": plan.attempt,
        "role": candidate.role, "projection_sha256": candidate.projection_sha256,
        "profile_id": projection.profile_id,
        "profile_sha256": candidate.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "source_files": manifest,
    }
    if candidate.candidate_id == "R194":
        identity.update({
            "r193_lineage_look_number": 4,
            "owner_one_time_exception": True,
        })
    elif candidate.candidate_id == "R195":
        identity.update({
            "r193_lineage_look_number": 5 if plan.attempt == 1 else 6,
            "owner_explicit_additional_look": True,
        })
        if plan.attempt == 2:
            identity.update({
                "r195_prior_attempts_spent": 1,
                "r193_prior_looks_spent": 5,
                "recovery_project_id": _R195_A2_PROJECT_ID,
            })
    return identity


def _require_valid_predecessor(plan: SettlementQcPlan) -> str:
    try:
        target_path_sha = prior._require_valid_predecessors(plan)
    except prior.SixUniverseTilt80SubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None
    if target_path_sha != _PREDECESSOR_TARGET_PATH_SHA256:
        _fail("settlement R182 target path changed")
    return target_path_sha


def _launch_target_path(plan: SettlementQcPlan) -> str | None:
    """Keep the old exact path gate; new looks bind their own runtime paths."""
    predecessor = _require_valid_predecessor(plan)
    return None if plan.candidate_id in _ALL_GUARDED_IDS else predecessor


def _require_r195_a1_recovery_claim(plan: SettlementQcPlan) -> str:
    """Authenticate the spent A1 claim and absence of any A1 launch receipt."""
    if plan.candidate_id != "R195" or plan.attempt != 2:
        _fail("R195 recovery requires its exact A2 plan")
    a1_plan = replace(plan, attempt=1)
    _require_valid_predecessor(a1_plan)
    claim = _read(_control_path(a1_plan, "claim"))
    files = claim.get("source_files")
    if (
        set(claim) != {
            "candidate_id", "attempt", "role", "projection_sha256", "profile_id",
            "profile_sha256", "package_sha256", "activation_manifest_sha256",
            "source_files", "r193_lineage_look_number",
            "owner_explicit_additional_look", "owner_launch_authority_mode",
            "owner_launch_waiver_schema", "owner_launch_waiver_id",
            "owner_waived_payload_sha256", "matched_baseline_target_path_sha256",
        }
        or claim.get("candidate_id") != "R195"
        or claim.get("attempt") != a1_plan.attempt
        or claim.get("role") != _CANDIDATES["R195"].role
        or claim.get("projection_sha256") != _CANDIDATES["R195"].projection_sha256
        or claim.get("profile_id") != ladder_projection.PROFILE_IDS[100]
        or claim.get("profile_sha256") != _CANDIDATES["R195"].profile_sha256
        or claim.get("package_sha256") != plan.package_sha256
        or claim.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or type(files) is not list or len(files) != _CANDIDATES["R195"].source_count
        or any(type(row) is not list or len(row) != 3
               or type(row[0]) is not str or type(row[1]) is not str
               or type(row[2]) is not int or row[2] <= 0 for row in files)
        or _manifest_digest(files) != _CANDIDATES["R195"].source_files_sha256
        or claim.get("r193_lineage_look_number") != 5
        or claim.get("owner_explicit_additional_look") is not True
        or claim.get("matched_baseline_target_path_sha256") is not None
        or claim.get("owner_launch_authority_mode")
        != "exact_exploratory_signature_waiver"
        or claim.get("owner_launch_waiver_schema")
        != "arv2-six-universe-r195-settlement-waiver-v1"
        or claim.get("owner_launch_waiver_id") != _CANDIDATES["R195"].waiver_id
        or claim.get("owner_waived_payload_sha256") != hashlib.sha256(
            _waiver_payload(a1_plan, claim, None)
        ).hexdigest()
        or any(_control_path(a1_plan, name).exists() for name in (
            "launch", "terminal", "result-read-claim", "result-valid",
        ))
    ):
        _fail("R195 A1 claim or no-launch recovery boundary changed")
    return hashlib.sha256(_canonical(claim)).hexdigest()


def _waiver_payload(plan: SettlementQcPlan, identity: dict,
                    target_path: str | None, *,
                    a1_claim_sha256: str | None = None) -> bytes:
    candidate = _candidate(plan)
    if candidate.candidate_id == "R203" and plan.attempt == 2:
        return _recent_adapter()._a2_waiver_payload(plan, identity, target_path)
    a2 = candidate.candidate_id == "R195" and plan.attempt == 2
    if a2 and (type(a1_claim_sha256) is not str
               or not _HEX.fullmatch(a1_claim_sha256)):
        _fail("R195 A2 waiver lacks the exact spent A1 claim")
    if candidate.candidate_id in _ALL_GUARDED_IDS:
        valid_path = target_path is None
    else:
        valid_path = target_path == _PREDECESSOR_TARGET_PATH_SHA256
    if not valid_path:
        _fail("settlement predecessor target path changed")
    payload = {
        "schema": f"arv2-six-universe-{candidate.candidate_id.lower()}-settlement-waiver-v1",
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_id": (
            _R195_A2_WAIVER_ID if a2 else candidate.waiver_id
        ),
        "action": ("one_existing_private_project_order_backtest_launch" if a2
                   else "one_private_exploratory_order_backtest_launch"),
        "candidate_id": candidate.candidate_id, "attempt": plan.attempt,
        "role": candidate.role,
        "organization_id_sha256": hashlib.sha256(
            plan.organization_id.encode("ascii")
        ).hexdigest(),
        "project_id": _R195_A2_PROJECT_ID if a2 else None,
        "project_name": candidate.project_name,
        "backtest_name": plan.backtest_name,
        "control_directory": str(plan.control_directory),
        "projection_sha256": candidate.projection_sha256,
        "profile_id": identity["profile_id"],
        "profile_sha256": candidate.profile_sha256,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "matched_baseline_target_path_sha256": target_path,
        "source_files_sha256": candidate.source_files_sha256,
        "mutating_endpoint_budget": (
            {"compile/create": 1, "backtests/create": 1} if a2 else {
                "projects/create": 1, "files/delete": 1,
                "files/create": candidate.source_count, "files/update": 1,
                "compile/create": 1, "backtests/create": 1,
            }
        ),
        "maximum_backtest_submissions": 1,
        "aggregate_only_result_read_authorized": True,
        "maximum_result_reads": 1,
        "raw_provider_rows_authorized": False,
        "raw_logs_orders_charts_authorized": False,
        "paper_live_deployment_funded_trading_authorized": False,
    }
    if candidate.candidate_id == "R194":
        payload.update({
            "r193_lineage_look_number": 4,
            "r193_prior_looks_spent": 3,
            "owner_one_time_exception": True,
            "maximum_additional_r193_lineage_submissions": 1,
        })
    elif candidate.candidate_id in _RECENT_PERCENTS:
        payload.update({
            "historical_r182_target_path_sha256": _PREDECESSOR_TARGET_PATH_SHA256,
            "matched_target_path_policy_id": "producer_derived_per_candidate_v1",
            "comparison_reference_candidate_id": "R203",
            "comparison_requires_valid_r203_exact_path": True,
            "matched_baseline_profile_sha256": _matched_profile_sha256(candidate),
            "evaluation_start_session": _RECENT_GEOMETRY[0],
            "evaluation_end_session": _RECENT_GEOMETRY[1],
            "evaluation_session_count": _RECENT_GEOMETRY[2],
            "decision_count": _RECENT_GEOMETRY[3],
            "input_upload_manifest_sha256": _recent_adapter().UPLOAD_MANIFEST_SHA256,
            "input_lineage_sha256": _recent_adapter().PINNED_LINEAGE_SHA256,
        })
    elif candidate.candidate_id in _LADDER_PERCENTS:
        payload.update({
            "historical_r182_target_path_sha256": _PREDECESSOR_TARGET_PATH_SHA256,
            "matched_target_path_policy_id": "producer_derived_per_candidate_v1",
            "comparison_reference_candidate_id": "R195",
            "comparison_requires_valid_r195_exact_path": True,
        })
        if candidate.candidate_id == "R195":
            if a2:
                payload.update({
                    "r193_lineage_look_number": 6,
                    "r193_prior_looks_spent": 5,
                    "r195_prior_attempts_spent": 1,
                    "a1_claim_sha256": a1_claim_sha256,
                    "source_upload_authorized": False,
                    "existing_project_id": _R195_A2_PROJECT_ID,
                    "owner_explicit_additional_look": True,
                    "maximum_additional_r193_lineage_submissions": 1,
                })
            else:
                payload.update({
                    "r193_lineage_look_number": 5,
                    "r193_prior_looks_spent": 4,
                    "owner_explicit_additional_look": True,
                    "maximum_additional_r193_lineage_submissions": 1,
                })
    return _canonical(payload)


def render_owner_waiver_payload(plan: SettlementQcPlan, projection: object) -> bytes:
    identity = preview(plan, projection)
    a1_sha = (_require_r195_a1_recovery_claim(plan)
              if plan.candidate_id == "R195" and plan.attempt == 2 else None)
    return _waiver_payload(
        plan, identity, _launch_target_path(plan), a1_claim_sha256=a1_sha,
    )


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
    if plan.attempt != 1:
        _fail("settlement A1 launcher requires attempt one")
    identity = preview(plan, projection)
    target_path = _launch_target_path(plan)
    if candidate.candidate_id in _RECENT_PERCENTS:
        _recent_adapter().require_uploaded_inputs(plan)
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
    if candidate.candidate_id == "R194":
        authority.update({
            "r193_lineage_look_number": 4,
            "owner_one_time_exception": True,
        })
    elif candidate.candidate_id == "R195":
        authority.update({
            "r193_lineage_look_number": 5,
            "owner_explicit_additional_look": True,
        })
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


def launch_r195_a2(
    plan: SettlementQcPlan, projection: object, api: QuantConnectClient, *,
    owner_waiver_id: str,
) -> dict:
    """Recover one R195 launch in the exact A1 project without uploading code."""
    candidate = _candidate(plan)
    if candidate.candidate_id != "R195" or plan.attempt != 2:
        _fail("R195 A2 recovery requires its exact second-attempt plan")
    identity = preview(plan, projection)
    a1_claim_sha = _require_r195_a1_recovery_claim(plan)
    target_path = _launch_target_path(plan)
    if type(owner_waiver_id) is not str or owner_waiver_id != _R195_A2_WAIVER_ID:
        _fail("R195 A2 owner waiver does not cover this recovery")
    authority = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": "arv2-six-universe-r195-settlement-waiver-v1",
        "owner_launch_waiver_id": _R195_A2_WAIVER_ID,
        "owner_waived_payload_sha256": hashlib.sha256(_waiver_payload(
            plan, identity, target_path, a1_claim_sha256=a1_claim_sha,
        )).hexdigest(),
        "r193_lineage_look_number": 6,
        "r193_prior_looks_spent": 5,
        "r195_prior_attempts_spent": 1,
        "owner_explicit_additional_look": True,
        "a1_claim_sha256": a1_claim_sha,
        "recovery_project_id": _R195_A2_PROJECT_ID,
    }
    claim_path = _control_path(plan, "claim")
    if claim_path.exists():
        _fail("R195 A2 attempt was already claimed")
    _client(api)
    _post(api, "authenticate", {})
    project_id = _R195_A2_PROJECT_ID
    projects = _post(api, "projects/read", {"projectId": project_id}).get("projects")
    if type(projects) is not list or len(projects) != 1 or type(projects[0]) is not dict:
        _fail("R195 A2 existing project is unavailable")
    row = projects[0]
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
        _fail("R195 A2 existing project is not exact, private, and idle")
    _check_uploaded_source(project_id, identity, api)
    inventory = _post(api, "backtests/list", {
        "projectId": project_id, "includeStatistics": False,
    })
    if (type(inventory.get("backtests")) is not list
            or inventory["backtests"] != [] or inventory.get("count") != 0):
        _fail("R195 A2 existing project has a prior or ambiguous backtest")
    _write(claim_path, {
        **identity, **authority,
        "matched_baseline_target_path_sha256": target_path,
    })
    started = _post(api, "compile/create", {"projectId": project_id})
    compile_id = started.get("compileId")
    if type(compile_id) is not str or not _ID.fullmatch(compile_id):
        _fail("R195 A2 compile identity changed")
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
            _fail("R195 A2 compile state changed")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            time.sleep(2)
    else:
        _fail("R195 A2 compile poll exhausted; attempt remains spent")
    if state["state"] == "BuildError":
        _write(_control_path(plan, "terminal"), {
            "candidate_id": "R195", "attempt": 2, "status": "BuildError",
            "project_id": project_id, "compile_id": compile_id,
        })
        _fail("R195 A2 compile failed; attempt was consumed")
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
        _fail("R195 A2 backtest launch identity changed")
    receipt = {
        **{key: value for key, value in identity.items() if key != "source_files"},
        **authority,
        "matched_baseline_target_path_sha256": target_path,
        "project_id": project_id, "project_name": candidate.project_name,
        "compile_id": compile_id, "backtest_id": launched["backtestId"],
        "backtest_name": plan.backtest_name,
    }
    _write(_control_path(plan, "launch"), receipt)
    return receipt


def _match_launch(plan: SettlementQcPlan, launch: dict) -> _Candidate:
    candidate = _candidate(plan)
    if type(launch) is not dict or (
        launch.get("candidate_id") != candidate.candidate_id
        or launch.get("attempt") != plan.attempt
        or launch.get("role") != candidate.role
        or launch.get("project_name") != candidate.project_name
        or launch.get("backtest_name") != plan.backtest_name
        or launch.get("projection_sha256") != candidate.projection_sha256
        or launch.get("profile_sha256") != candidate.profile_sha256
        or launch.get("matched_baseline_target_path_sha256")
        != (None if candidate.candidate_id in _ALL_GUARDED_IDS
            else _PREDECESSOR_TARGET_PATH_SHA256)
        or type(launch.get("project_id")) is not int
        or launch["project_id"] <= 0
        or type(launch.get("backtest_id")) is not str
        or not _ID.fullmatch(launch["backtest_id"])
    ):
        _fail("settlement launch receipt differs from exact plan")
    if candidate.candidate_id == "R194" and (
        launch.get("r193_lineage_look_number") != 4
        or launch.get("owner_one_time_exception") is not True
    ):
        _fail("R194 is not bound to the fourth R193-lineage look")
    if candidate.candidate_id == "R195":
        if plan.attempt == 1 and (
            launch.get("r193_lineage_look_number") != 5
            or launch.get("owner_explicit_additional_look") is not True
        ):
            _fail("R195 A1 is not bound to the fifth R193-lineage look")
        if plan.attempt == 2 and (
            launch.get("r193_lineage_look_number") != 6
            or launch.get("r193_prior_looks_spent") != 5
            or launch.get("r195_prior_attempts_spent") != 1
            or launch.get("owner_explicit_additional_look") is not True
            or launch.get("recovery_project_id") != _R195_A2_PROJECT_ID
            or launch.get("project_id") != _R195_A2_PROJECT_ID
            or type(launch.get("a1_claim_sha256")) is not str
            or not _HEX.fullmatch(launch["a1_claim_sha256"])
        ):
            _fail("R195 A2 recovery launch identity changed")
    if candidate.candidate_id == "R203" and plan.attempt == 2:
        _recent_adapter()._require_a2_launch(plan, launch)
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
        row.get("name") != plan.backtest_name
        or ("projectId" in row and row["projectId"] != launch["project_id"])
        or status not in {
            "In Queue...", "In Progress...", "Completed.", "Runtime Error",
        }
    ):
        _fail("settlement backtest status identity changed")
    if status in {"Completed.", "Runtime Error"}:
        terminal = {
            "candidate_id": candidate.candidate_id, "status": status,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        if plan.attempt == 2:
            terminal["attempt"] = 2
        _write(terminal_path, terminal)
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
_TILT_FRACTIONS = {
    "R192": "0.80", "R193": "1.00", "R194": "1.00",
    "R195": "1.00", "R196": "1.20", "R197": "1.40",
    "R198": "1.60", "R199": "1.80", "R200": "2.00",
    "R201": "2.50", "R202": "3.00",
    "R203": "1.00", "R204": "1.20", "R205": "1.40",
    "R206": "1.60", "R207": "1.80", "R208": "2.00",
}


def _exact_result_claim(
    plan: SettlementQcPlan, launch: dict, candidate: _Candidate,
) -> dict:
    """Rebind source, predecessor and waiver before consuming the one read."""
    claim = _read(_control_path(plan, "claim"))
    source_files = claim.get("source_files")
    target_path = _launch_target_path(plan)
    if (
        claim.get("candidate_id") != candidate.candidate_id
        or claim.get("attempt") != plan.attempt
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
    if candidate.candidate_id == "R194" and (
        claim.get("r193_lineage_look_number") != 4
        or claim.get("owner_one_time_exception") is not True
        or launch.get("r193_lineage_look_number") != 4
        or launch.get("owner_one_time_exception") is not True
    ):
        _fail("R194 claim did not persist the one-time fourth lineage look")
    if candidate.candidate_id == "R195" and plan.attempt == 1 and (
        claim.get("r193_lineage_look_number") != 5
        or claim.get("owner_explicit_additional_look") is not True
        or launch.get("r193_lineage_look_number") != 5
        or launch.get("owner_explicit_additional_look") is not True
    ):
        _fail("R195 claim did not persist the fifth R193-lineage look")
    a1_claim_sha = None
    if candidate.candidate_id == "R195" and plan.attempt == 2:
        a1_claim_sha = _require_r195_a1_recovery_claim(plan)
        if (
            claim.get("r193_lineage_look_number") != 6
            or claim.get("r193_prior_looks_spent") != 5
            or claim.get("r195_prior_attempts_spent") != 1
            or claim.get("owner_explicit_additional_look") is not True
            or claim.get("recovery_project_id") != _R195_A2_PROJECT_ID
            or claim.get("a1_claim_sha256") != a1_claim_sha
            or any(claim.get(key) != launch.get(key) for key in (
                "r193_lineage_look_number", "r193_prior_looks_spent",
                "r195_prior_attempts_spent", "owner_explicit_additional_look",
                "recovery_project_id", "a1_claim_sha256",
            ))
        ):
            _fail("R195 A2 claim did not persist its exact recovery lineage")
    waiver_sha = hashlib.sha256(
        _waiver_payload(plan, claim, target_path,
                        a1_claim_sha256=a1_claim_sha)
    ).hexdigest()
    if (
        claim.get("owner_launch_authority_mode")
        != "exact_exploratory_signature_waiver"
        or claim.get("owner_launch_waiver_schema") != (
            f"arv2-six-universe-{candidate.candidate_id.lower()}-settlement-waiver-v1"
        )
        or claim.get("owner_launch_waiver_id") != (
            _R195_A2_WAIVER_ID if candidate.candidate_id == "R195"
            and plan.attempt == 2 else _recent_adapter()._A2_WAIVER_ID
            if candidate.candidate_id == "R203" and plan.attempt == 2
            else candidate.waiver_id
        )
        or claim.get("owner_waived_payload_sha256") != waiver_sha
        or any(claim.get(key) != launch.get(key) for key in (
            "owner_launch_authority_mode", "owner_launch_waiver_schema",
            "owner_launch_waiver_id", "owner_waived_payload_sha256",
        ))
    ):
        _fail("settlement owner waiver receipt changed")
    return claim


def _settlement_aggregate(
    aggregate: dict, candidate: _Candidate, *, matched_target_path: str | None,
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
            or execution.get("submitted_rebalance_count") != (
                _RECENT_GEOMETRY[3] if candidate.candidate_id in _RECENT_PERCENTS
                else base_runtime.EXPECTED_DECISION_COUNT
            )
            or execution.get("completed_rebalance_count") != (
                _RECENT_GEOMETRY[3] if candidate.candidate_id in _RECENT_PERCENTS
                else base_runtime.EXPECTED_DECISION_COUNT
            )
            or execution.get("submitted_order_count")
            != execution.get("filled_order_count_sum")
            or execution.get("invalid_order_count_sum") != 0
            or execution.get("canceled_order_count_sum") != 0
            or execution.get("execution_failure") is not False
        ))
    ):
        _fail("settlement order, exposure, or tracking validity changed")
    if candidate.candidate_id in _ALL_GUARDED_IDS:
        observed_path = aggregate.get("matched_baseline_target_path_sha256")
        if type(observed_path) is not str or not _HEX.fullmatch(observed_path):
            _fail("settlement producer-derived matched target path is invalid")
    if candidate.candidate_id in _TILT_FRACTIONS and (
        aggregate.get("matched_baseline_profile_sha256")
        != _matched_profile_sha256(candidate)
        or (candidate.candidate_id not in _ALL_GUARDED_IDS
            and aggregate.get("matched_baseline_target_path_sha256")
            != matched_target_path)
        or aggregate.get("maximum_stock_weight_change_fraction")
        != _TILT_FRACTIONS[candidate.candidate_id]
    ):
        _fail("settlement tilt or matched target binding changed")
    base = {key: aggregate[key] for key in cap90._AGGREGATE_FIELDS}
    try:
        selected = cap90._project_aggregate(
            base, bridge=False,
            expected_geometry=(_RECENT_GEOMETRY
                               if candidate.candidate_id in _RECENT_PERCENTS else None),
        )
    except cap90.Cap90QcSubmissionError as exc:
        raise SixUniverseSettlementSubmissionError(str(exc)) from None
    selected.update({key: aggregate[key] for key in _SETTLEMENT_FIELDS | tilt_fields})
    selected["execution"].update({
        "mean_target_weight_l1_error": execution["mean_target_weight_l1_error"],
        "maximum_target_weight_l1_error": execution["maximum_target_weight_l1_error"],
    })
    return selected


def _verified_ladder_result_receipt(plan: SettlementQcPlan) -> dict | None:
    """Authenticate one local result chain without another QC result read."""
    candidate = _candidate(plan)
    if candidate.candidate_id not in _ALL_GUARDED_IDS:
        _fail("settlement receipt comparison requires a guarded tilt candidate")
    valid_path = _control_path(plan, "result-valid")
    if not valid_path.exists():
        return None
    try:
        launch = _read(_control_path(plan, "launch"))
        _match_launch(plan, launch)
        _exact_result_claim(plan, launch, candidate)
        terminal = {
            "candidate_id": candidate.candidate_id, "status": "Completed.",
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        read_claim = {
            "candidate_id": candidate.candidate_id,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        if plan.attempt == 2:
            terminal["attempt"] = 2
            read_claim["attempt"] = 2
        if _read(_control_path(plan, "terminal")) != terminal:
            return None
        if _read(_control_path(plan, "result-read-claim")) != read_claim:
            return None
        receipt = _read(valid_path)
    except SixUniverseSettlementSubmissionError:
        return None
    expected = {
        "candidate_id", "attempt", "run_valid", "aggregate_sha256",
        "projection_sha256", "profile_sha256", "project_id", "backtest_id",
        "matched_baseline_target_path_sha256", "matched_baseline_profile_sha256",
        "package_sha256", "activation_manifest_sha256", "source_files_sha256",
        "comparison_valid",
    }
    if candidate.candidate_id == "R195" and plan.attempt == 2:
        expected.update({
            "r193_lineage_look_number", "r193_prior_looks_spent",
            "r195_prior_attempts_spent", "a1_claim_sha256",
            "recovery_project_id",
        })
    if (
        set(receipt) != expected
        or receipt.get("candidate_id") != candidate.candidate_id
        or receipt.get("attempt") != plan.attempt
        or receipt.get("run_valid") is not True
        or receipt.get("projection_sha256") != candidate.projection_sha256
        or receipt.get("profile_sha256") != candidate.profile_sha256
        or receipt.get("project_id") != launch["project_id"]
        or receipt.get("backtest_id") != launch["backtest_id"]
        or receipt.get("matched_baseline_profile_sha256")
        != _matched_profile_sha256(candidate)
        or receipt.get("package_sha256") != plan.package_sha256
        or receipt.get("activation_manifest_sha256")
        != plan.activation_manifest_sha256
        or receipt.get("source_files_sha256") != candidate.source_files_sha256
        or type(receipt.get("comparison_valid")) is not bool
        or (candidate.candidate_id in {"R195", "R203"}
            and receipt.get("comparison_valid") is not False)
        or type(receipt.get("aggregate_sha256")) is not str
        or not _HEX.fullmatch(receipt["aggregate_sha256"])
        or type(receipt.get("matched_baseline_target_path_sha256")) is not str
        or not _HEX.fullmatch(receipt["matched_baseline_target_path_sha256"])
    ):
        return None
    if candidate.candidate_id == "R195" and plan.attempt == 2 and (
        receipt.get("r193_lineage_look_number") != 6
        or receipt.get("r193_prior_looks_spent") != 5
        or receipt.get("r195_prior_attempts_spent") != 1
        or receipt.get("a1_claim_sha256") != launch.get("a1_claim_sha256")
        or receipt.get("recovery_project_id") != _R195_A2_PROJECT_ID
    ):
        return None
    return receipt


def _valid_r195_comparison_anchor(plan: SettlementQcPlan) -> tuple[int, str] | None:
    """Select exactly one valid R195 attempt as the matched-path anchor."""
    found = []
    for attempt in (1, 2):
        anchor_plan = SettlementQcPlan(
            "R195", plan.organization_id, plan.package_sha256,
            plan.activation_manifest_sha256, plan.control_directory, attempt,
        )
        receipt = _verified_ladder_result_receipt(anchor_plan)
        if receipt is not None:
            found.append((attempt, receipt["matched_baseline_target_path_sha256"]))
    return found[0] if len(found) == 1 else None


def compare_valid_receipts(plan: SettlementQcPlan) -> dict:
    """Reconcile frozen R195 and a later result without QC calls or rewrites."""
    candidate = _candidate(plan)
    if candidate.candidate_id in _RECENT_PERCENTS:
        if candidate.candidate_id == "R203":
            _fail("recent comparison requires a later recent-window A1 plan")
        observed = _verified_ladder_result_receipt(plan)
        anchor = _recent_adapter()._valid_comparison_anchor(plan)
        return {
            "candidate_id": candidate.candidate_id,
            "comparison_valid": (
                observed is not None and anchor is not None
                and observed["matched_baseline_target_path_sha256"] == anchor[1]
            ),
            "r203_anchor_attempt": None if anchor is None else anchor[0],
            "matched_baseline_target_path_sha256": (
                None if observed is None else observed["matched_baseline_target_path_sha256"]
            ),
            "r203_matched_baseline_target_path_sha256": (
                None if anchor is None else anchor[1]
            ),
        }
    if candidate.candidate_id not in _LATER_LADDER_CANDIDATES:
        _fail("settlement comparison requires a later guarded ladder A1 plan")
    observed = _verified_ladder_result_receipt(plan)
    anchor = _valid_r195_comparison_anchor(plan)
    return {
        "candidate_id": candidate.candidate_id,
        "comparison_valid": (
            observed is not None and anchor is not None
            and observed["matched_baseline_target_path_sha256"] == anchor[1]
        ),
        "r195_anchor_attempt": None if anchor is None else anchor[0],
        "matched_baseline_target_path_sha256": (
            None if observed is None else observed["matched_baseline_target_path_sha256"]
        ),
        "r195_matched_baseline_target_path_sha256": (
            None if anchor is None else anchor[1]
        ),
    }


def read_aggregates_once(
    plan: SettlementQcPlan, launch: dict, api: QuantConnectClient,
) -> dict:
    """Consume one bounded custom-statistic read after exact completion."""
    candidate = _match_launch(plan, launch)
    if _read(_control_path(plan, "launch")) != launch:
        _fail("settlement launch receipt changed")
    expected_terminal = {
        "candidate_id": candidate.candidate_id, "status": "Completed.",
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    }
    if plan.attempt == 2:
        expected_terminal["attempt"] = 2
    if _read(_control_path(plan, "terminal")) != expected_terminal:
        _fail("settlement exact run did not complete")
    read_path = _control_path(plan, "result-read-claim")
    if read_path.exists():
        _fail("settlement result read was already claimed")
    claim = _exact_result_claim(plan, launch, candidate)
    _client(api)
    _check_uploaded_source(launch["project_id"], claim, api)
    read_claim = {
        "candidate_id": candidate.candidate_id,
        "project_id": launch["project_id"],
        "backtest_id": launch["backtest_id"],
    }
    if plan.attempt == 2:
        read_claim["attempt"] = 2
    _write(read_path, read_claim)
    response = _post(api, "backtests/read", {
        "projectId": launch["project_id"],
        "backtestId": launch["backtest_id"],
    })
    backtest = response.get("backtest")
    if type(backtest) is not dict or (
        backtest.get("projectId") != launch["project_id"]
        or backtest.get("backtestId") != launch["backtest_id"]
        or backtest.get("name") != plan.backtest_name
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
        matched_target_path=(
            None if candidate.candidate_id in _ALL_GUARDED_IDS
            else _PREDECESSOR_TARGET_PATH_SHA256
        ),
    )
    valid = aggregate["run_valid"] is True
    comparison_valid = False
    if valid and candidate.candidate_id in _LATER_LADDER_CANDIDATES:
        anchor = _valid_r195_comparison_anchor(plan)
        comparison_valid = (
            anchor is not None
            and selected["matched_baseline_target_path_sha256"] == anchor[1]
        )
    elif valid and candidate.candidate_id in _RECENT_PERCENTS and candidate.candidate_id != "R203":
        anchor = _recent_adapter()._valid_comparison_anchor(plan)
        comparison_valid = (
            anchor is not None
            and selected["matched_baseline_target_path_sha256"]
            == anchor[1]
        )
    if valid:
        receipt = {
            "candidate_id": candidate.candidate_id, "attempt": plan.attempt,
            "run_valid": True, "aggregate_sha256": meta["aggregate_sha256"],
            "projection_sha256": candidate.projection_sha256,
            "profile_sha256": candidate.profile_sha256,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"],
        }
        if candidate.candidate_id in _ALL_GUARDED_IDS:
            receipt.update({
                "matched_baseline_target_path_sha256": (
                    selected["matched_baseline_target_path_sha256"]
                ),
                "matched_baseline_profile_sha256": (
                    _matched_profile_sha256(candidate)
                ),
                "package_sha256": plan.package_sha256,
                "activation_manifest_sha256": plan.activation_manifest_sha256,
                "source_files_sha256": candidate.source_files_sha256,
                "comparison_valid": comparison_valid,
            })
        if candidate.candidate_id == "R195" and plan.attempt == 2:
            receipt.update({
                "r193_lineage_look_number": 6,
                "r193_prior_looks_spent": 5,
                "r195_prior_attempts_spent": 1,
                "a1_claim_sha256": launch["a1_claim_sha256"],
                "recovery_project_id": _R195_A2_PROJECT_ID,
            })
        _write(_control_path(plan, "result-valid"), receipt)
    result = {"meta": meta, "aggregates": selected, "run_valid": valid}
    if candidate.candidate_id in _ALL_GUARDED_IDS:
        result["comparison_valid"] = comparison_valid
    if candidate.candidate_id == "R195" and plan.attempt == 2:
        result.update({
            "r193_lineage_look_number": 6,
            "r193_prior_looks_spent": 5,
            "r195_prior_attempts_spent": 1,
        })
    return result


__all__ = (
    "SettlementQcPlan", "SixUniverseSettlementSubmissionError",
    "compare_valid_receipts", "launch_a1", "launch_r195_a2", "poll_status",
    "preview", "read_aggregates_once", "render_owner_waiver_payload",
)
