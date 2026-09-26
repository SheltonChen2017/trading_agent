"""Offline immutable Sep25 successor to the exact reviewed Sep16 inputs.

The old package and its historical contributions are never rewritten. Ratings
whose eligibility fell beyond its cutoff are recovered from its original
archive; only Sep17--25 event dates are acquired separately by the caller.
Current-snapshot identity and vendor-version risks remain explicitly accepted,
not point-in-time guarantees. This module has no provider or QC transport.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2.canonical import parse_utc_timestamp
from research.analyst_revisions_v2.global_benchmark_contract import (
    require_loaded_global_benchmark_contract,
)

from . import accepted_risk_delta_order_package as _old
from . import accepted_risk_preliminary_package as _compact
from . import accepted_risk_preliminary_rating_evaluator as _evaluator
from . import physical_accepted_risk_archive as _archive
from .production_evidence_composer import (
    require_section72_owner_waived_firm_admission,
)


LINEAGE_SCHEMA = "arv2-accepted-risk-latest-order-input-lineage-v1"
FRESH_FIRST_EVENT_DATE = "2026-09-17"
FRESH_LAST_EVENT_DATE = "2026-09-25"
DECISION_CUTOFF_SESSION = "2026-09-25"
FINAL_EXECUTION_SESSION = "2026-09-25"
FRESH_CUTOFF_CLOSE_AT = "2026-09-25T20:00:00.000000Z"


class LatestOrderInputPackageError(ValueError):
    """A fixed predecessor, new archive or preserved input invariant changed."""


@dataclasses.dataclass(frozen=True, slots=True)
class LatestOrderInputPackage:
    package: _compact.AcceptedRiskPreliminaryPackage
    lineage_bytes: bytes
    lineage_sha256: str
    decision_cutoff_session: str
    final_execution_session: str
    recovered_tail_contribution_count: int
    fresh_contribution_count: int

    @property
    def lineage(self):
        """A detached disclosure copy, never mutable wrapper authority."""
        return json.loads(self.lineage_bytes.decode("ascii"))


def require_latest_order_input_package(value):
    """Check immutable disclosure against the authenticated compact package.

    The wrapper grants no capability. A future QC caller must additionally
    supply its independently frozen package/source/profile identities.
    """
    if type(value) is not LatestOrderInputPackage or type(value.lineage_bytes) is not bytes:
        _refuse("latest input wrapper or lineage type changed")
    _compact.require_accepted_risk_preliminary_package(value.package)
    try:
        lineage = value.lineage
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LatestOrderInputPackageError("latest input lineage is unreadable") from exc
    if (type(lineage) is not dict or _compact._canonical(lineage) != value.lineage_bytes
            or hashlib.sha256(value.lineage_bytes).hexdigest() != value.lineage_sha256
            or value.package.source_disposition_sha256 != value.lineage_sha256
            or lineage.get("schema") != LINEAGE_SCHEMA
            or value.decision_cutoff_session != DECISION_CUTOFF_SESSION
            or value.final_execution_session != FINAL_EXECUTION_SESSION
            or lineage.get("decision_cutoff_session") != value.decision_cutoff_session
            or lineage.get("final_execution_session") != value.final_execution_session
            or type(value.recovered_tail_contribution_count) is not int
            or type(value.fresh_contribution_count) is not int
            or lineage.get("recovered_tail_contribution_count") != value.recovered_tail_contribution_count
            or lineage.get("fresh_contribution_count") != value.fresh_contribution_count):
        _refuse("latest input lineage or wrapper binding changed")
    return value


def _refuse(message):
    raise LatestOrderInputPackageError(message)


def _sha(value):
    return hashlib.sha256(_compact._canonical(value)).hexdigest()


def _sessions():
    result = tuple(
        item.isoformat() for item in trading_sessions(
            date.fromisoformat(_old.RATING_HISTORY_START_SESSION),
            date.fromisoformat(FINAL_EXECUTION_SESSION),
        )
    )
    if (not result or result[0] != _old.RATING_HISTORY_START_SESSION
            or result[-1] != FINAL_EXECUTION_SESSION
            or DECISION_CUTOFF_SESSION not in result):
        _refuse("latest input session axis changed")
    return result


def _extend_memberships(prior_sessions, memberships, sessions):
    prior_axis = tuple(row["session"] for row in prior_sessions)
    if (not prior_axis or prior_axis[-1] != _old.FINAL_EXECUTION_SESSION
            or sessions[:len(prior_axis)] != prior_axis
            or len(sessions) <= len(prior_axis)):
        _refuse("latest input axis does not preserve the predecessor prefix")
    extended = []
    count = 0
    for row in memberships:
        if row["last_session_index_exclusive"] == len(prior_axis):
            count += 1
            extended.append(_evaluator.build_membership_record(
                security_id=row["security_id"],
                first_session_index=row["first_session_index"],
                last_session_index_exclusive=len(sessions),
                sector_id=row["sector_id"],
            ))
        else:
            extended.append(dict(row))
    if not count:
        _refuse("latest input has no predecessor-active membership to extend")
    return tuple(sorted(extended, key=lambda row: (
        row["security_id"], row["first_session_index"],
        row["last_session_index_exclusive"], row["sector_id"],
    ))), count


def _archive_binding(value):
    return {
        "archive_id": value.archive_id,
        "archive_sha256": value.archive_sha256,
        "source_manifest_sha256": value.source_manifest_sha256,
        "pair_sha256": value.pair_sha256,
        "capture_started_at": value.capture_started_at,
        "capture_completed_at": value.capture_completed_at,
        "first_event_date": value.requested_first_event_date,
        "last_event_date": value.requested_last_event_date,
        "source_row_count": value.source_row_count,
    }


def _authenticate_archives(parent, delta, fresh):
    values = tuple(_archive.require_physical_accepted_risk_archive(value)
                   for value in (parent, delta, fresh))
    if any(value.capture_transport != "massive_https_bearer_default_session"
           for value in values):
        _refuse("latest input requires production physical archives")
    if (parent.archive_id != _old.EXPECTED_PARENT_ARCHIVE_ID
            or parent.archive_sha256 != _old.EXPECTED_PARENT_ARCHIVE_SHA256
            or delta.archive_id != _old.EXPECTED_DELTA_ARCHIVE_ID
            or delta.archive_sha256 != _old.EXPECTED_DELTA_ARCHIVE_SHA256):
        _refuse("latest input predecessor archive identity changed")
    if (fresh.requested_first_event_date != FRESH_FIRST_EVENT_DATE
            or fresh.requested_last_event_date != FRESH_LAST_EVENT_DATE
            or parse_utc_timestamp(fresh.capture_started_at, "fresh capture start")
            < parse_utc_timestamp(FRESH_CUTOFF_CLOSE_AT, "fresh cutoff close")
            or parse_utc_timestamp(fresh.capture_completed_at, "fresh capture end")
            < parse_utc_timestamp(fresh.capture_started_at, "fresh capture start")
            or tuple(role for role, _ in fresh.role_row_counts) != (
                MassiveSourceRole.ANALYST_RATINGS, MassiveSourceRole.EARNINGS,
                MassiveSourceRole.CORPORATE_GUIDANCE,
            )):
        _refuse("latest input fresh capture range, clock or role census changed")
    return values


def _cross_boundary_rating_events(parent, delta, fresh):
    """Quarantine fresh reused rating IDs without altering predecessor rows."""
    fresh_ids = set()
    for row in _archive.iter_physical_accepted_risk_rows(fresh):
        if (row.locator.source_role is MassiveSourceRole.ANALYST_RATINGS
                and row.provider_event_id is not None):
            fresh_ids.add(row.provider_event_id)
    collisions = set()
    for old_archive in (parent, delta):
        for row in _archive.iter_physical_accepted_risk_rows(old_archive):
            if (row.locator.source_role is MassiveSourceRole.ANALYST_RATINGS
                    and row.provider_event_id in fresh_ids):
                collisions.add(_compact._PINNED_COMMON_EVENT_ID(row.provider_event_id))
    return frozenset(collisions)


def _merge_preserved_contributions(prior, rederived, fresh, cutoff, collisions):
    """Preserve all old records; quarantine new cross-archive daily conflicts."""
    prior_by_id = {row["contribution_id"]: row for row in prior}
    if len(prior_by_id) != len(prior) or any(
            row["eligible_session_index"] > cutoff for row in prior):
        _refuse("latest input predecessor contribution census changed")
    tail = []
    for row in rederived:
        if row["eligible_session_index"] <= cutoff:
            if prior_by_id.get(row["contribution_id"]) != row:
                _refuse("latest input rederived predecessor contribution changed")
        else:
            tail.append(row)
    admitted_fresh = [row for row in fresh
                      if row["eligible_session_index"] > cutoff
                      and row["common_event_id"] not in collisions]
    groups = defaultdict(list)
    for origin, rows in (("tail", tail), ("fresh", admitted_fresh)):
        for row in rows:
            key = (row["source_view_id"], row["eligible_session_index"],
                   row["security_id"], row["institution_id"])
            groups[key].append((origin, row))
    selected = []
    origin_counts = Counter()
    ambiguous = 0
    disposition = []
    for key, group in sorted(groups.items()):
        # The old normalizer already handles same-archive daily dedupe. Any
        # remaining multi-row group crosses archives and is refused as a whole.
        accepted = len(group) == 1
        if not accepted:
            ambiguous += 1
        for origin, row in sorted(group, key=lambda value: value[1]["contribution_id"]):
            disposition.append({
                "contribution_id": row["contribution_id"], "origin": origin,
                "disposition": "accepted" if accepted else "cross_archive_daily_ambiguity",
            })
            if accepted:
                selected.append(row)
                origin_counts[origin] += 1
    combined = _old._merge_contributions(prior, tuple(selected))
    combined_by_id = {row["contribution_id"]: row for row in combined}
    if any(combined_by_id.get(identifier) != row
           for identifier, row in prior_by_id.items()):
        _refuse("latest input changed a preserved contribution")
    return combined, {
        "recovered_tail_contribution_count": origin_counts["tail"],
        "fresh_contribution_count": origin_counts["fresh"],
        "cross_boundary_rating_event_refusal_count": len(collisions),
        "cross_archive_daily_ambiguity_count": ambiguous,
    }, _sha(disposition)


def build_latest_order_input_package(
    *, old_delta_package_path: Path, parent_archive, prior_delta_archive,
    fresh_archive, firm_admission, global_contract, output_root: Path,
) -> LatestOrderInputPackage:
    """Build one fixed Sep25 successor from authenticated offline inputs."""
    predecessor = _old.load_accepted_risk_delta_order_package(
        old_delta_package_path,
        expected_package_sha256=_old.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=_old.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    parent, delta, fresh = _authenticate_archives(
        parent_archive, prior_delta_archive, fresh_archive,
    )
    firms = require_section72_owner_waived_firm_admission(firm_admission)
    contract = require_loaded_global_benchmark_contract(global_contract)
    if (firms.admission_sha256 != _old.EXPECTED_FIRM_ADMISSION_SHA256
            or contract.map_hash != _old.EXPECTED_GLOBAL_MAP_SHA256):
        _refuse("latest input firm or global mapping identity changed")
    prior_manifest, roles = _old._load_prior_roles(predecessor.package)
    sessions = _sessions()
    memberships, extension_count = _extend_memberships(
        roles["session_axis"], roles["memberships"], sessions,
    )
    collision_events = _cross_boundary_rating_events(parent, delta, fresh)
    ticker_map = _old._known_ticker_map(roles["runtime_symbol_bindings"])
    with tempfile.TemporaryDirectory(prefix="arv2-latest-contributions-") as scratch:
        derived = []
        for label, archive in (("tail", delta), ("fresh", fresh)):
            derived.append(_compact._derive_contributions(
                archive=archive, sessions=sessions, ticker_to_security=ticker_map,
                firm_admission=firms, global_contract=contract,
                spool_path=Path(scratch) / (label + ".sqlite3"),
                maximum_eligible_session=DECISION_CUTOFF_SESSION,
            ))
    old_cutoff = sessions.index(_old.DELTA_DECISION_END_SESSION)
    if sum(row["eligible_session_index"] <= old_cutoff
           for row in derived[0][0]) != predecessor.delta_contribution_count:
        _refuse("latest input rederived delta census changed")
    contributions, appended_census, merge_disposition = _merge_preserved_contributions(
        roles["contributions"], derived[0][0], derived[1][0],
        old_cutoff, collision_events,
    )
    security_sha = prior_manifest["source_lineage_sha256s"]["security_master_admission_sha256"]
    lineage = {
        "schema": LINEAGE_SCHEMA,
        "predecessor_package_id": predecessor.package.package_id,
        "predecessor_package_sha256": predecessor.package.package_sha256,
        "predecessor_lineage_sha256": predecessor.lineage_sha256,
        "parent_archive": _archive_binding(parent),
        "prior_delta_archive": _archive_binding(delta),
        "fresh_archive": _archive_binding(fresh),
        "tail_source_disposition_sha256": derived[0][1],
        "fresh_source_disposition_sha256": derived[1][1],
        "merge_disposition_sha256": merge_disposition,
        "predecessor_contribution_stream_sha256": _compact._stream_hash(roles["contributions"]),
        "combined_contribution_stream_sha256": _compact._stream_hash(contributions),
        "security_master_admission_sha256": security_sha,
        "firm_ontology_admission_sha256": firms.admission_sha256,
        "global_rating_map_sha256": contract.map_hash,
        "session_count": len(sessions),
        "decision_cutoff_session": DECISION_CUTOFF_SESSION,
        "final_execution_session": FINAL_EXECUTION_SESSION,
        "extended_membership_count": extension_count,
        **appended_census,
        "historical_contributions_unchanged": True,
        "security_policy": "extend_only_predecessor_active_known_FIGI_memberships;unknown_tickers_refuse",
        "duplicate_policy": "preserve_predecessor;quarantine_fresh_reused_rating_IDs_and_new_cross_archive_daily_groups",
        "point_in_time_security_master": False, "pristine_point_in_time": False,
        "provider_access": False, "quantconnect_access": False,
        "outcome_access": False, "orders": False, "trading": False,
    }
    lineage_sha = _sha(lineage)
    manifest = _evaluator.build_preliminary_rating_manifest(
        benchmark_security_id=_compact.BENCHMARK_SECURITY_ID,
        session_axis_records=_old._session_records(sessions),
        membership_records=memberships, contribution_records=contributions,
        source_lineage_sha256s={
            "accepted_risk_input_pair_sha256": lineage_sha,
            "security_master_admission_sha256": security_sha,
            "firm_ontology_admission_sha256": firms.admission_sha256,
            "global_rating_map_sha256": contract.map_hash,
            "pre_normalized_contribution_source_sha256": lineage_sha,
        },
        history_batch_security_count=_compact.HISTORY_BATCH_SECURITY_COUNT,
        scoring_sessions_per_callback=_compact.SCORING_SESSIONS_PER_CALLBACK,
        signal_seed_contributions_per_callback=_compact.SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK,
    )
    census = {
        "preserved_contribution_count": len(roles["contributions"]),
        "combined_contribution_count": len(contributions), **appended_census,
        **{"tail_" + key: value for key, value in derived[0][2].items()},
        **{"fresh_" + key: value for key, value in derived[1][2].items()},
    }
    package = _compact._materialize(
        output_root=output_root, evaluator_manifest=manifest,
        session_records=_old._session_records(sessions),
        membership_records=memberships, contribution_records=contributions,
        runtime_binding_records=roles["runtime_symbol_bindings"],
        source_disposition_sha256=lineage_sha, contribution_census=census,
    )
    return require_latest_order_input_package(LatestOrderInputPackage(
        package, _compact._canonical(lineage), lineage_sha, DECISION_CUTOFF_SESSION,
        FINAL_EXECUTION_SESSION, appended_census["recovered_tail_contribution_count"],
        appended_census["fresh_contribution_count"],
    ))


__all__ = [
    "LatestOrderInputPackage", "LatestOrderInputPackageError",
    "build_latest_order_input_package", "DECISION_CUTOFF_SESSION", "FINAL_EXECUTION_SESSION",
    "require_latest_order_input_package",
]
