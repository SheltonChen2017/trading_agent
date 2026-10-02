"""Extend the reviewed compact rating input through the 2026 data cutoff.

This is deliberately a narrow, accepted-risk successor.  It reuses the exact
reviewed security/FIGI inventory from the prior compact package, extends only
memberships that were active at the 2025 cutoff, and names every 2026 rating
whose current-restated ticker is absent from that inventory as a refusal.  It
does not claim a refreshed point-in-time security master.

The resulting object is still an input package: its own capability disclosure
continues to say ``orders=False``.  A separate backtest-only projection must
grant simulated-order capability; this module performs no QC, price, outcome,
result, broker, deployment, order, or trading I/O.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import NoReturn

from data.exchange_calendar import ExchangeCalendarError, trading_sessions
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContract,
    require_loaded_global_benchmark_contract,
)

from . import accepted_risk_preliminary_package as _prior
from . import accepted_risk_preliminary_rating_evaluator as _evaluator
from .accepted_risk_massive_delta import (
    ParentBoundMassiveDelta,
    require_parent_bound_massive_delta,
)
from .accepted_risk_preliminary_package import (
    AcceptedRiskPreliminaryPackage,
    AcceptedRiskPreliminaryPackageError,
    iter_accepted_risk_preliminary_upload_objects,
    load_accepted_risk_preliminary_package,
    require_accepted_risk_preliminary_package,
)
from .production_evidence_composer import (
    OwnerWaivedAcceptedRiskFirmAdmission,
    require_section72_owner_waived_firm_admission,
)


class AcceptedRiskDeltaOrderPackageError(ValueError):
    """The fixed delta successor or one of its parents is not exact."""


LINEAGE_SCHEMA = "arv2-accepted-risk-delta-order-input-lineage-v1"
RATING_HISTORY_START_SESSION = "2013-01-02"
PRIOR_DECISION_END_SESSION = "2025-12-31"
DELTA_DECISION_END_SESSION = "2026-09-16"
FINAL_EXECUTION_SESSION = "2026-09-17"
WINDOW_START_SESSIONS = ("2025-01-02", "2026-01-02")
EXPECTED_PRIOR_PACKAGE_SHA256 = (
    "e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9"
)
EXPECTED_COMPOSITE_SHA256 = (
    "0dc8a581fd2cff4113b1264f28a239ff92d66261f5069bf2ee6bebb18edcb8c9"
)
EXPECTED_COMPOSITE_ROW_PROJECTION_SHA256 = (
    "c053f537e809a4729766561114c07c2891a52daa41bcedd876dc323262e1e44d"
)
EXPECTED_FIRM_ADMISSION_SHA256 = (
    "cbdb0e8b4d529d32d01688dc80a2292af8b3329aa2023ccf6b55ad5ee2af2f0c"
)
EXPECTED_SECURITY_MASTER_ADMISSION_SHA256 = (
    "5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281"
)
EXPECTED_GLOBAL_MAP_SHA256 = (
    "aaf5830c3c3fb403b0e84f5ad22d1f20fa3f91df41cf3bd64f33695875d2e3d9"
)
EXPECTED_DELTA_PACKAGE_ID = (
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
EXPECTED_DELTA_PACKAGE_SHA256 = (
    "7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f"
)
EXPECTED_DELTA_LINEAGE_SHA256 = (
    "54723703380d5011420d8a364cf857a9978092b6b1d0daaa4d367dc1c65fb129"
)
EXPECTED_PRIOR_PACKAGE_ID = (
    "arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2"
)
EXPECTED_PRIOR_SOURCE_DISPOSITION_SHA256 = (
    "3828998a5c8011d75bc7c5ddb211741731fc6af99227054152b260a82ec7890c"
)
EXPECTED_PARENT_ARCHIVE_ID = (
    "arv2-physical-accepted-risk-83ef125320d6a74ce9e4ba1c"
)
EXPECTED_PARENT_ARCHIVE_SHA256 = (
    "83ef125320d6a74ce9e4ba1c2003f396d076a23d310bcafadf76774b7316bd11"
)
EXPECTED_PARENT_PAIR_SHA256 = (
    "aeb5cbae4adf4e19174b5c2404a250b0cd3dc0a6de67272c3ba07e8e3c2ee94a"
)
EXPECTED_DELTA_ARCHIVE_ID = (
    "arv2-physical-accepted-risk-1678b925bc78e8b3f4fdf291"
)
EXPECTED_DELTA_ARCHIVE_SHA256 = (
    "1678b925bc78e8b3f4fdf2911e3e426327fb8a1307463d1ff2bd43f279a1cc77"
)
EXPECTED_DELTA_PAIR_SHA256 = (
    "0452a4811db397068b0dbd4c0e22db92c1597bcfcef93559e71647ee87228ea8"
)
EXPECTED_COMPOSITE_ID = (
    "arv2-parent-bound-massive-delta-0dc8a581fd2cff4113b1264f"
)
EXPECTED_COMPOSITE_ROW_COUNT = 962_999
# Filled from the authenticated, already-built delta source-disposition fold.
# It is a lineage pin, never a credential, provider row, or outcome value.
EXPECTED_DELTA_SOURCE_DISPOSITION_SHA256 = (
    "8b42a7b09bcf3be4a0c913edd05ac8cf32952e7351ea5f6265f9200c2e5a78e0"
)


def _refuse(message: str) -> NoReturn:
    raise AcceptedRiskDeltaOrderPackageError(message)


def _sha_record(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _lineage_record(
    *,
    prior_package_id: str,
    prior_package_sha256: str,
    prior_source_disposition_sha256: str,
    parent_archive_id: str,
    parent_archive_sha256: str,
    parent_pair_sha256: str,
    delta_archive_id: str,
    delta_archive_sha256: str,
    delta_pair_sha256: str,
    composite_id: str,
    composite_sha256: str,
    composite_row_projection_sha256: str,
    composite_row_count: int,
    delta_source_disposition_sha256: str,
    security_master_admission_sha256: str,
    firm_ontology_admission_sha256: str,
    global_rating_map_sha256: str,
    session_count: int,
    prior_contribution_count: int,
    delta_contribution_count: int,
    combined_contribution_count: int,
    extended_membership_count: int,
) -> dict[str, object]:
    """Return the one canonical lineage shape shared by build and reload."""

    return {
        "schema": LINEAGE_SCHEMA,
        "prior_package_id": prior_package_id,
        "prior_package_sha256": prior_package_sha256,
        "prior_source_disposition_sha256": prior_source_disposition_sha256,
        "parent_archive_id": parent_archive_id,
        "parent_archive_sha256": parent_archive_sha256,
        "parent_pair_sha256": parent_pair_sha256,
        "delta_archive_id": delta_archive_id,
        "delta_archive_sha256": delta_archive_sha256,
        "delta_pair_sha256": delta_pair_sha256,
        "composite_id": composite_id,
        "composite_sha256": composite_sha256,
        "composite_row_projection_sha256": composite_row_projection_sha256,
        "composite_row_count": composite_row_count,
        "delta_source_disposition_sha256": delta_source_disposition_sha256,
        "security_master_admission_sha256": security_master_admission_sha256,
        "firm_ontology_admission_sha256": firm_ontology_admission_sha256,
        "global_rating_map_sha256": global_rating_map_sha256,
        "rating_history_start_session": RATING_HISTORY_START_SESSION,
        "decision_cutoff_session": DELTA_DECISION_END_SESSION,
        "final_execution_session": FINAL_EXECUTION_SESSION,
        "window_start_sessions": list(WINDOW_START_SESSIONS),
        "session_count": session_count,
        "prior_contribution_count": prior_contribution_count,
        "delta_contribution_count": delta_contribution_count,
        "combined_contribution_count": combined_contribution_count,
        "extended_membership_count": extended_membership_count,
        "security_policy": (
            "reuse_exact_reviewed_current_snapshot_FIGI_inventory_and_extend_"
            "only_memberships_active_at_2025_cutoff;_unknown_2026_tickers_refuse"
        ),
        "current_snapshot_identity_only": True,
        "refreshed_security_master": False,
        "point_in_time_security_master": False,
        "survivorship_free": False,
        "provider_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "orders": False,
        "trading": False,
    }


def _load_prior_roles(
    package: AcceptedRiskPreliminaryPackage,
) -> tuple[dict[str, object], dict[str, tuple[dict[str, object], ...]]]:
    manifest: dict[str, object] | None = None
    rows: dict[str, list[dict[str, object]]] = {
        "session_axis": [],
        "memberships": [],
        "contributions": [],
        "runtime_symbol_bindings": [],
    }
    for descriptor, payload in iter_accepted_risk_preliminary_upload_objects(
        package
    ):
        if descriptor.role == "activation_manifest":
            continue
        if descriptor.role == "evaluator_manifest":
            try:
                decoded = json.loads(payload.decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AcceptedRiskDeltaOrderPackageError(
                    "prior evaluator manifest is unreadable"
                ) from exc
            if (
                type(decoded) is not dict
                or _prior._canonical(decoded) + b"\n" != payload
                or manifest is not None
            ):
                _refuse("prior evaluator manifest is not exact canonical JSON")
            manifest = decoded
            continue
        if descriptor.role not in rows or descriptor.compression != "gzip":
            _refuse("prior package role inventory changed")
        loaded, _byte_count = _prior._load_canonical_gzip_records(
            payload, descriptor
        )
        rows[descriptor.role].extend(loaded)
    if manifest is None or any(not value for value in rows.values()):
        _refuse("prior package omits a required authenticated role")
    return manifest, {name: tuple(value) for name, value in rows.items()}


def _successor_sessions() -> tuple[str, ...]:
    try:
        sessions = tuple(
            item.isoformat()
            for item in trading_sessions(
                date.fromisoformat(RATING_HISTORY_START_SESSION),
                date.fromisoformat(FINAL_EXECUTION_SESSION),
            )
        )
    except (ExchangeCalendarError, ValueError) as exc:
        raise AcceptedRiskDeltaOrderPackageError(
            "delta order session axis is unavailable"
        ) from exc
    if (
        len(sessions) != 3_448
        or sessions[0] != RATING_HISTORY_START_SESSION
        or sessions[-1] != FINAL_EXECUTION_SESSION
        or DELTA_DECISION_END_SESSION not in sessions
        or any(start not in sessions for start in WINDOW_START_SESSIONS)
    ):
        _refuse("delta order session axis changed")
    return sessions


def _session_records(sessions: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "schema": _evaluator.SESSION_SCHEMA,
            "session": session,
            "session_index": index,
        }
        for index, session in enumerate(sessions)
    )


def _extend_memberships(
    prior_sessions: tuple[dict[str, object], ...],
    prior_memberships: tuple[dict[str, object], ...],
    successor_session_count: int,
) -> tuple[tuple[dict[str, object], ...], int]:
    prior_axis = tuple(row.get("session") for row in prior_sessions)
    if (
        not prior_axis
        or prior_axis != tuple(sorted(set(prior_axis)))
        or PRIOR_DECISION_END_SESSION not in prior_axis
    ):
        _refuse("prior package session axis changed")
    active_exclusive = prior_axis.index(PRIOR_DECISION_END_SESSION) + 1
    extended: list[dict[str, object]] = []
    extension_count = 0
    for row in prior_memberships:
        if type(row) is not dict:
            _refuse("prior membership row changed type")
        last = row.get("last_session_index_exclusive")
        if type(last) is not int:
            _refuse("prior membership interval changed type")
        if last == active_exclusive:
            extension_count += 1
            extended.append(
                _evaluator.build_membership_record(
                    security_id=row.get("security_id"),
                    first_session_index=row.get("first_session_index"),
                    last_session_index_exclusive=successor_session_count,
                    sector_id=row.get("sector_id"),
                )
            )
        else:
            extended.append(dict(row))
    extended.sort(
        key=lambda row: (
            row["security_id"],
            row["first_session_index"],
            row["last_session_index_exclusive"],
            row["sector_id"],
        )
    )
    if extension_count < 1:
        _refuse("no prior active membership survived the delta cutoff")
    return tuple(extended), extension_count


def _known_ticker_map(
    bindings: tuple[dict[str, object], ...],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in bindings:
        if type(row) is not dict:
            _refuse("prior runtime binding row changed type")
        ticker = row.get("diagnostic_current_ticker")
        security_id = row.get("security_id")
        if (
            type(ticker) is not str
            or not ticker
            or type(security_id) is not str
            or not security_id
        ):
            _refuse("prior runtime binding identity changed")
        if ticker in result:
            _refuse("prior runtime binding ticker became ambiguous")
        result[ticker] = security_id
    return result


def _merge_contributions(
    prior_rows: tuple[dict[str, object], ...],
    delta_rows: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    combined = tuple((*prior_rows, *delta_rows))
    keys = [
        (
            _evaluator.SOURCE_VIEW_IDS.index(row["source_view_id"]),
            row["eligible_session_index"],
            row["security_id"],
            row["institution_id"],
            row["contribution_id"],
        )
        for row in combined
    ]
    if len(set(row["contribution_id"] for row in combined)) != len(combined):
        _refuse("prior and delta contribution identities overlap")
    result = tuple(
        row for _key, row in sorted(zip(keys, combined, strict=True))
    )
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskDeltaOrderPackage:
    package: AcceptedRiskPreliminaryPackage
    lineage: dict[str, object]
    lineage_sha256: str
    prior_contribution_count: int
    delta_contribution_count: int
    extended_membership_count: int
    decision_cutoff_session: str
    final_execution_session: str
    current_snapshot_identity_only: bool
    refreshed_security_master: bool
    provider_access: bool
    quantconnect_access: bool
    outcome_access: bool
    orders: bool
    trading: bool


def build_accepted_risk_delta_order_package(
    *,
    composite: ParentBoundMassiveDelta,
    prior_package: AcceptedRiskPreliminaryPackage,
    firm_admission: OwnerWaivedAcceptedRiskFirmAdmission,
    global_contract: GlobalBenchmarkContract,
    output_root: Path,
) -> AcceptedRiskDeltaOrderPackage:
    """Build the fixed known-identity 2026 input successor without external I/O."""

    composite = require_parent_bound_massive_delta(composite)
    prior_package = require_accepted_risk_preliminary_package(prior_package)
    firm_admission = require_section72_owner_waived_firm_admission(
        firm_admission
    )
    global_contract = require_loaded_global_benchmark_contract(global_contract)
    if (
        prior_package.package_sha256 != EXPECTED_PRIOR_PACKAGE_SHA256
        or composite.composite_sha256 != EXPECTED_COMPOSITE_SHA256
        or composite.row_projection_sha256
        != EXPECTED_COMPOSITE_ROW_PROJECTION_SHA256
        or firm_admission.admission_sha256 != EXPECTED_FIRM_ADMISSION_SHA256
        or global_contract.map_hash != EXPECTED_GLOBAL_MAP_SHA256
    ):
        _refuse("delta order package parent identity changed")

    prior_manifest, roles = _load_prior_roles(prior_package)
    sessions = _successor_sessions()
    session_records = _session_records(sessions)
    memberships, extended_count = _extend_memberships(
        roles["session_axis"], roles["memberships"], len(sessions)
    )
    ticker_to_security = _known_ticker_map(
        roles["runtime_symbol_bindings"]
    )
    scratch = Path(tempfile.mkdtemp(prefix="arv2-delta-order-package-"))
    try:
        delta_rows, delta_disposition_sha256, delta_census = (
            _prior._derive_contributions(
                archive=composite.delta_archive,
                sessions=sessions,
                ticker_to_security=ticker_to_security,
                firm_admission=firm_admission,
                global_contract=global_contract,
                spool_path=scratch / "delta-contributions.sqlite3",
                maximum_eligible_session=DELTA_DECISION_END_SESSION,
            )
        )
    finally:
        shutil.rmtree(scratch)
    contributions = _merge_contributions(
        roles["contributions"], delta_rows
    )
    prior_lineage = prior_manifest.get("source_lineage_sha256s")
    if type(prior_lineage) is not dict:
        _refuse("prior evaluator source lineage changed")
    security_master_sha256 = prior_lineage.get(
        "security_master_admission_sha256"
    )
    if type(security_master_sha256) is not str:
        _refuse("prior security-master lineage changed")
    lineage = _lineage_record(
        prior_package_id=prior_package.package_id,
        prior_package_sha256=prior_package.package_sha256,
        prior_source_disposition_sha256=(
            prior_package.source_disposition_sha256
        ),
        parent_archive_id=composite.parent_archive.archive_id,
        parent_archive_sha256=composite.parent_archive.archive_sha256,
        parent_pair_sha256=composite.parent_archive.pair_sha256,
        delta_archive_id=composite.delta_archive.archive_id,
        delta_archive_sha256=composite.delta_archive.archive_sha256,
        delta_pair_sha256=composite.delta_archive.pair_sha256,
        composite_id=composite.composite_id,
        composite_sha256=composite.composite_sha256,
        composite_row_projection_sha256=composite.row_projection_sha256,
        composite_row_count=composite.admitted_row_count,
        delta_source_disposition_sha256=delta_disposition_sha256,
        security_master_admission_sha256=security_master_sha256,
        firm_ontology_admission_sha256=firm_admission.admission_sha256,
        global_rating_map_sha256=global_contract.map_hash,
        session_count=len(sessions),
        prior_contribution_count=len(roles["contributions"]),
        delta_contribution_count=len(delta_rows),
        combined_contribution_count=len(contributions),
        extended_membership_count=extended_count,
    )
    lineage_sha256 = _sha_record(lineage)
    manifest = _evaluator.build_preliminary_rating_manifest(
        benchmark_security_id=_prior.BENCHMARK_SECURITY_ID,
        session_axis_records=session_records,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s={
            # This legacy field receives the parent-bound composite root; the
            # exact changed semantics are explicit in ``lineage`` above.
            "accepted_risk_input_pair_sha256": composite.composite_sha256,
            "security_master_admission_sha256": security_master_sha256,
            "firm_ontology_admission_sha256": firm_admission.admission_sha256,
            "global_rating_map_sha256": global_contract.map_hash,
            "pre_normalized_contribution_source_sha256": lineage_sha256,
        },
        history_batch_security_count=_prior.HISTORY_BATCH_SECURITY_COUNT,
        scoring_sessions_per_callback=_prior.SCORING_SESSIONS_PER_CALLBACK,
        signal_seed_contributions_per_callback=(
            _prior.SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK
        ),
    )
    census = {
        "prior_selected_contribution_count": len(roles["contributions"]),
        "delta_selected_contribution_count": len(delta_rows),
        "combined_selected_contribution_count": len(contributions),
        **{
            "delta_" + key: value
            for key, value in sorted(delta_census.items())
        },
    }
    package = _prior._materialize(
        output_root=output_root,
        evaluator_manifest=manifest,
        session_records=session_records,
        membership_records=memberships,
        contribution_records=contributions,
        runtime_binding_records=roles["runtime_symbol_bindings"],
        source_disposition_sha256=lineage_sha256,
        contribution_census=census,
    )
    return AcceptedRiskDeltaOrderPackage(
        package=package,
        lineage=lineage,
        lineage_sha256=lineage_sha256,
        prior_contribution_count=len(roles["contributions"]),
        delta_contribution_count=len(delta_rows),
        extended_membership_count=extended_count,
        decision_cutoff_session=DELTA_DECISION_END_SESSION,
        final_execution_session=FINAL_EXECUTION_SESSION,
        current_snapshot_identity_only=True,
        refreshed_security_master=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
        orders=False,
        trading=False,
    )


def _reconstruct_persisted_lineage(
    package: AcceptedRiskPreliminaryPackage,
    manifest: dict[str, object],
    roles: dict[str, tuple[dict[str, object], ...]],
) -> tuple[dict[str, object], int, int, int]:
    """Reconstruct the delta wrapper solely from authenticated package state."""

    expected_sessions = _successor_sessions()
    if roles.get("session_axis") != _session_records(expected_sessions):
        _refuse("persisted delta package session axis changed")
    memberships = roles.get("memberships")
    contributions = roles.get("contributions")
    bindings = roles.get("runtime_symbol_bindings")
    if (
        type(memberships) is not tuple
        or type(contributions) is not tuple
        or type(bindings) is not tuple
        or not memberships
        or not contributions
        or not bindings
    ):
        _refuse("persisted delta package role census changed")
    extended_membership_count = 0
    for row in memberships:
        if type(row) is not dict:
            _refuse("persisted delta membership row changed type")
        last = row.get("last_session_index_exclusive")
        if type(last) is not int:
            _refuse("persisted delta membership interval changed type")
        if last == len(expected_sessions):
            extended_membership_count += 1
    if extended_membership_count < 1:
        _refuse("persisted delta package has no extended membership")

    try:
        census = dict(package.contribution_census)
    except (TypeError, ValueError) as exc:
        raise AcceptedRiskDeltaOrderPackageError(
            "persisted delta package contribution census is unreadable"
        ) from exc
    count_names = (
        "prior_selected_contribution_count",
        "delta_selected_contribution_count",
        "combined_selected_contribution_count",
    )
    if any(type(census.get(name)) is not int for name in count_names):
        _refuse("persisted delta package contribution census changed")
    prior_count = census[count_names[0]]
    delta_count = census[count_names[1]]
    combined_count = census[count_names[2]]
    if (
        prior_count < 1
        or delta_count < 1
        or combined_count != prior_count + delta_count
        or combined_count != len(contributions)
    ):
        _refuse("persisted delta package contribution census changed")

    source_lineage = manifest.get("source_lineage_sha256s")
    if type(source_lineage) is not dict:
        _refuse("persisted delta evaluator source lineage changed")
    expected_manifest_values = {
        "benchmark_security_id": _prior.BENCHMARK_SECURITY_ID,
        "rating_history_start_session": RATING_HISTORY_START_SESSION,
        "session_axis_count": len(expected_sessions),
        "membership_row_count": len(memberships),
        "contribution_row_count": len(contributions),
        "history_batch_security_count": _prior.HISTORY_BATCH_SECURITY_COUNT,
        "scoring_sessions_per_callback": _prior.SCORING_SESSIONS_PER_CALLBACK,
        "signal_seed_contributions_per_callback": (
            _prior.SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK
        ),
        "source_view_ids": list(_evaluator.SOURCE_VIEW_IDS),
    }
    if any(
        manifest.get(name) != expected
        for name, expected in expected_manifest_values.items()
    ):
        _refuse("persisted delta evaluator profile changed")
    security_master_sha256 = source_lineage.get(
        "security_master_admission_sha256"
    )
    if (
        source_lineage.get("accepted_risk_input_pair_sha256")
        != EXPECTED_COMPOSITE_SHA256
        or security_master_sha256 != EXPECTED_SECURITY_MASTER_ADMISSION_SHA256
        or source_lineage.get("firm_ontology_admission_sha256")
        != EXPECTED_FIRM_ADMISSION_SHA256
        or source_lineage.get("global_rating_map_sha256")
        != EXPECTED_GLOBAL_MAP_SHA256
        or source_lineage.get("pre_normalized_contribution_source_sha256")
        != package.source_disposition_sha256
    ):
        _refuse("persisted delta evaluator input lineage changed")
    lineage = _lineage_record(
        prior_package_id=EXPECTED_PRIOR_PACKAGE_ID,
        prior_package_sha256=EXPECTED_PRIOR_PACKAGE_SHA256,
        prior_source_disposition_sha256=(
            EXPECTED_PRIOR_SOURCE_DISPOSITION_SHA256
        ),
        parent_archive_id=EXPECTED_PARENT_ARCHIVE_ID,
        parent_archive_sha256=EXPECTED_PARENT_ARCHIVE_SHA256,
        parent_pair_sha256=EXPECTED_PARENT_PAIR_SHA256,
        delta_archive_id=EXPECTED_DELTA_ARCHIVE_ID,
        delta_archive_sha256=EXPECTED_DELTA_ARCHIVE_SHA256,
        delta_pair_sha256=EXPECTED_DELTA_PAIR_SHA256,
        composite_id=EXPECTED_COMPOSITE_ID,
        composite_sha256=EXPECTED_COMPOSITE_SHA256,
        composite_row_projection_sha256=(
            EXPECTED_COMPOSITE_ROW_PROJECTION_SHA256
        ),
        composite_row_count=EXPECTED_COMPOSITE_ROW_COUNT,
        delta_source_disposition_sha256=(
            EXPECTED_DELTA_SOURCE_DISPOSITION_SHA256
        ),
        security_master_admission_sha256=security_master_sha256,
        firm_ontology_admission_sha256=EXPECTED_FIRM_ADMISSION_SHA256,
        global_rating_map_sha256=EXPECTED_GLOBAL_MAP_SHA256,
        session_count=len(expected_sessions),
        prior_contribution_count=prior_count,
        delta_contribution_count=delta_count,
        combined_contribution_count=combined_count,
        extended_membership_count=extended_membership_count,
    )
    return lineage, prior_count, delta_count, extended_membership_count


def load_accepted_risk_delta_order_package(
    path: Path,
    *,
    expected_package_sha256: str,
    expected_lineage_sha256: str,
) -> AcceptedRiskDeltaOrderPackage:
    """Reopen the exact immutable delta package without rebuilding parents."""

    if (
        type(expected_package_sha256) is not str
        or expected_package_sha256 != EXPECTED_DELTA_PACKAGE_SHA256
        or type(expected_lineage_sha256) is not str
        or expected_lineage_sha256 != EXPECTED_DELTA_LINEAGE_SHA256
    ):
        _refuse("persisted delta package out-of-band identity pin changed")
    try:
        package = load_accepted_risk_preliminary_package(
            path,
            expected_package_sha256=expected_package_sha256,
        )
    except AcceptedRiskPreliminaryPackageError as exc:
        raise AcceptedRiskDeltaOrderPackageError(
            "persisted delta package artifacts did not authenticate"
        ) from exc
    if (
        package.package_id != EXPECTED_DELTA_PACKAGE_ID
        or package.package_sha256 != EXPECTED_DELTA_PACKAGE_SHA256
        or package.source_disposition_sha256 != expected_lineage_sha256
    ):
        _refuse("persisted delta package root identity changed")
    manifest, roles = _load_prior_roles(package)
    lineage, prior_count, delta_count, extended_count = (
        _reconstruct_persisted_lineage(package, manifest, roles)
    )
    lineage_sha256 = _sha_record(lineage)
    if (
        lineage_sha256 != expected_lineage_sha256
        or lineage_sha256 != package.source_disposition_sha256
    ):
        _refuse("persisted delta package lineage did not reconstruct")
    require_accepted_risk_preliminary_package(package)
    return AcceptedRiskDeltaOrderPackage(
        package=package,
        lineage=lineage,
        lineage_sha256=lineage_sha256,
        prior_contribution_count=prior_count,
        delta_contribution_count=delta_count,
        extended_membership_count=extended_count,
        decision_cutoff_session=DELTA_DECISION_END_SESSION,
        final_execution_session=FINAL_EXECUTION_SESSION,
        current_snapshot_identity_only=True,
        refreshed_security_master=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
        orders=False,
        trading=False,
    )


__all__ = (
    "AcceptedRiskDeltaOrderPackage",
    "AcceptedRiskDeltaOrderPackageError",
    "DELTA_DECISION_END_SESSION",
    "EXPECTED_DELTA_LINEAGE_SHA256",
    "EXPECTED_DELTA_PACKAGE_ID",
    "EXPECTED_DELTA_PACKAGE_SHA256",
    "FINAL_EXECUTION_SESSION",
    "LINEAGE_SCHEMA",
    "RATING_HISTORY_START_SESSION",
    "WINDOW_START_SESSIONS",
    "build_accepted_risk_delta_order_package",
    "load_accepted_risk_delta_order_package",
)
